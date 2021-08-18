import json
from base64 import b64decode
from datetime import datetime
from os import environ
from pathlib import Path

import requests
import requests_cache
from furl import furl


class GithubAPIException(Exception):
    ...


class GithubAPIFileTooLarge(GithubAPIException):
    ...


class GithubClient:
    """
    A connection to the Github API
    Optionally uses request caching
    """

    user_agent = environ.get("GITHUB_USER_AGENT", "")
    base_url = "https://api.github.com"

    def __init__(
        self, use_cache=False, token=None, expire_after=-1, urls_expire_after=None
    ):
        token = token or environ.get("GITHUB_TOKEN", None)
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": self.user_agent,
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
        if use_cache:
            self.session = requests_cache.CachedSession(
                backend="sqlite",
                cache_name=environ.get("REQUESTS_CACHE_NAME", "http_cache"),
                expire_after=expire_after,
                urls_expire_after=urls_expire_after,
            )
        else:
            self.session = requests.Session()

    def get_json(self, path_segments, **add_args):
        """
        Builds and calls a url from the base and path segments
        Returns the response as json
        """
        f = furl(self.base_url)
        f.path.segments += path_segments
        if add_args:
            f.add(add_args)
        response = self.session.get(f.url, headers=self.headers)

        # Report some expected errors
        if response.status_code == 403:
            errors = response.json().get("errors")
            if errors:
                for error in errors:
                    if error["code"] == "too_large":
                        raise GithubAPIFileTooLarge("Error: File too large")
            else:
                raise GithubAPIException(json.dumps(response.json()))
        elif response.status_code == 404:
            raise GithubAPIException(response.json()["message"])
        # raise any other unexpected status
        response.raise_for_status()
        response_json = response.json()
        return response_json

    def get_repo(self, owner_and_repo):
        """
        Ensure a repo exists and return a GithubRepo
        """
        owner, repo = owner_and_repo.split("/")
        repo_path_seqments = ["repos", owner, repo]
        # call it to raise exceptions in case it doesn't exist
        self.get_json(repo_path_seqments)
        return GithubRepo(self, owner, repo)


class GithubRepo:
    """
    Fetch contents of a Github Repo
    """

    def __init__(self, client, owner, name):
        self.client = client
        self.owner = owner
        self.name = name
        self.repo_path_segments = ["repos", owner, name]
        self._url = None

    @property
    def url(self):
        if self._url is None:
            self._url = f"https://github.com/{self.owner}/{self.name}"
        return self._url

    def get_pull_requests(self, state="open", page=1):
        path_segments = [*self.repo_path_segments, "pulls"]
        return self.client.get_json(path_segments, state=state, page=page, per_page=30)

    def pull_request_count(self, state):
        """
        Get the total pull request count for this repo.  By default PRs are returned in
        pages of 30 per page.

        Args:
            state (str): open, closed, all
        Returns:
            int
        """
        page = 1
        pr_count = len(self.get_pull_requests(state=state, page=page))
        if pr_count < 30:
            return pr_count
        total_pr_count = pr_count
        while pr_count == 30:
            page += 1
            pr_count = len(self.get_pull_requests(state=state, page=page))
            total_pr_count += pr_count
        return total_pr_count

    @property
    def open_pull_request_count(self):
        """
        Count of open pull requests
        Returns:
            int
        """
        return self.pull_request_count("open")

    def get_branches(self):
        path_segments = [*self.repo_path_segments, "branches"]
        return self.client.get_json(path_segments)

    @property
    def branch_count(self):
        """
        Count of open repo branches
        Returns:
            int
        """
        return len(self.get_branches())

    def get_contents(self, path, ref, return_fetch_type=False, from_git_blob=False):
        """
        Fetch the contents of a path and ref (branch/commit/tag)

        Args:
            path (str): path to the file in the repo
            ref (str): branch/tag/sha
            return_fetch_type (bool): Also return the fetch type, "content" or "blob"
            use_git_blob (bool): Fetch the contents via git blob without trying to get
            contents directly first

        Returns:
             a single GithubContentFile if the path is a single file, or a list
            of GithubContentFiles if the path is a folder
            Optionally returns the fetch type

        """
        path_segments = [*self.repo_path_segments, "contents", *path.split("/")]

        if from_git_blob:
            contents = self.get_contents_from_git_blob(path, ref)
            fetch_type = "blob"

        else:
            fetch_type = "contents"
            try:
                contents = self.client.get_json(path_segments, ref=ref)
            except GithubAPIFileTooLarge:
                # If the file is too big, retrieve it from the git blob instead
                contents = self.get_contents_from_git_blob(path, ref)
                fetch_type = "blob"

        if isinstance(contents, list):
            contents = [
                GithubContentFile.from_json({**content}) for content in contents
            ]
        else:
            contents["last_updated"] = self.get_last_updated(path, ref)
            contents = GithubContentFile.from_json(contents)

        if return_fetch_type:
            return contents, fetch_type
        return contents

    def get_parent_contents(self, path, ref):
        parent_folder_path = str(Path(path).parent)
        return self.get_contents(parent_folder_path, ref)

    def matching_file_from_parent_contents(self, path, ref):
        """
        Given a filepath, return the first matching file from the file's parent folder
        Args:
            path (str): path to the file in the repo
            ref (str): branch/tag/sha
        Returns:
            GithubContentFile
        """
        file_name = Path(path).name
        return next(
            (
                content_file
                for content_file in self.get_parent_contents(path, ref)
                if content_file.name == file_name
            ),
            None,
        )

    def get_contents_from_git_blob(self, path, ref):
        """
        Get all the content files from the parent folder (this doesn't download the actual
        content itself, but returns a list of GithubContentFile objects, from which we can
        obtain sha for the relevant file)
        Args:
            path (str): path to the file in the repo
            ref (str): branch/tag/sha
        Returns:
            dicts
        """
        # Find the file in the parent folder whose name matches the file we want
        matching_content_file = self.matching_file_from_parent_contents(path, ref)
        blob = self.get_git_blob(matching_content_file.sha)
        return blob

    def get_git_blob(self, sha):
        """
        Fetch a git blob by sha
        Args:
            sha (str): commit sha
        Returns:
            dict
        """
        path_segments = [*self.repo_path_segments, "git", "blobs", sha]
        return self.client.get_json(path_segments)

    def get_commits_for_file(self, path, ref, number_of_commits=1):
        """
        Fetches commits for a file (just the latest commit by default)
        Args:
            path (str): path to the file in the repo
            ref (str): branch/tag/sha
            number_of_commits (str): number of commits to return (default 1)
        Returns:
            list of dicts: one for each commit
        """
        path_segments = [*self.repo_path_segments, "commits"]
        response = self.client.get_json(
            path_segments, sha=ref, path=path, per_page=number_of_commits
        )
        return response

    def get_last_updated(self, path, ref):
        """
        Find the date of the last commit for a file
        Args:
            path (str): path to the file in the repo
            ref (str): branch/tag/sha
        Returns:
            str: HTML from readme (at ROOT)
        """
        commits = self.get_commits_for_file(path, ref, number_of_commits=1)
        last_commit_date = commits[0]["commit"]["committer"]["date"]
        return datetime.strptime(last_commit_date, "%Y-%m-%dT%H:%M:%SZ").date()

    def get_readme(self, tag="main"):
        """
        Fetches the README.md of repo
        Args:
            tag (str): tag that you want the readme for.
        Returns:
            str: HTML from readme (at ROOT)
        """
        path_segments = [*self.repo_path_segments, "readme"]
        content = self.client.get_json(path_segments, ref=tag)
        content_file = GithubContentFile.from_json({**content})
        return content_file.decoded_content

    def get_repo_details(self):
        """
        Fetches the About and Name of the repo
        Returns:
            dict: 2 key dictionary with about and name as keys
        """
        response = self.client.get_json(self.repo_path_segments)
        description = response["description"]
        name = response["name"]
        return {"name": name, "about": description}

    def get_tags(self):
        """
        Gets a list of tags associated with a repo
        Returns:
            List of Dicts (1 per tag), with keys 'tag_name' and 'sha'
        """
        path_segments = [*self.repo_path_segments, "tags"]
        content = self.client.get_json(path_segments)
        simple_tag_list = [
            {"tag_name": tag["name"], "sha": tag["commit"]["sha"]} for tag in content
        ]
        return simple_tag_list

    def get_commit(self, sha):
        """
        Get details of a specific commit
        Args:
            sha (str): commit sha
        Returns:
            Dict: Details of commit, with keys of 'author' and 'date'
        """
        path_segments = [*self.repo_path_segments, "git", "commits", sha]
        content = self.client.get_json(path_segments)
        return {
            "author": content["author"]["name"],
            "date": content["committer"]["date"],
        }

    def clear_cache(self):
        """Clear all request cache urls for this repo"""
        cached_urls = list(self.client.session.cache.urls)
        repo_path = f"{self.owner}/{self.name}".lower()
        for cached_url in cached_urls:
            if repo_path in cached_url.lower():
                self.client.session.cache.delete_url(cached_url)


class GithubContentFile:
    """Holds information about a single file in a repo"""

    def __init__(self, name, last_updated, content, sha):
        self.name = name
        self.last_updated = last_updated
        self.content = content
        self.sha = sha

    @classmethod
    def from_json(cls, json_input):
        return cls(
            name=json_input.get("name"),
            content=json_input.get("content"),
            last_updated=json_input.get("last_updated"),
            sha=json_input["sha"],
        )

    @property
    def decoded_content(self):
        # self.content may be None when /contents has returned a list of files
        if self.content:
            return b64decode(self.content).decode("utf-8")
