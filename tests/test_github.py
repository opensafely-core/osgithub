import json
from base64 import b64encode
from datetime import date
from os import environ

import pytest
from requests.exceptions import HTTPError

from osgithub import GithubAPIException, GithubClient, GithubRepo

from .conftest import remove_cache_file_if_exists


def register_commits_uri(httpretty, owner, repo, path, sha, commit_dates):
    commit_dates = (
        [commit_dates] if not isinstance(commit_dates, list) else commit_dates
    )
    httpretty.register_uri(
        httpretty.GET,
        f"https://api.github.com/repos/{owner}/{repo}/commits?sha={sha}&path={path}",
        status=200,
        body=json.dumps(
            [
                {"commit": {"committer": {"date": commit_date}}}
                for commit_date in commit_dates
            ]
        ),
    )


def test_github_client_get_repo(httpretty):
    # Mock the github request
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo",
        status=200,
        body=json.dumps({"name": "foo"}),
    )
    client = GithubClient()
    repo = client.get_repo("test/foo")
    assert repo.repo_path_segments == ["repos", "test", "foo"]


def test_github_client_token(reset_environment_after_test):
    """Authorization headers is set based on environment variable"""
    environ["GITHUB_TOKEN"] = "test"
    client = GithubClient()
    assert client.headers["Authorization"] == "token test"

    del environ["GITHUB_TOKEN"]
    client = GithubClient()
    assert "Authorization" not in client.headers


def test_github_client_get_repo_not_found(httpretty):
    # Mock the github request
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/bar",
        status=404,
        body=json.dumps({"message": "Not found"}),
    )
    client = GithubClient()
    with pytest.raises(GithubAPIException, match="Not found"):
        client.get_repo("test/bar")


@pytest.mark.parametrize("use_cache", [True, False])
def test_github_client_get_repo_with_cache(httpretty, use_cache):
    client = GithubClient(use_cache=use_cache)

    # set up mock request with valid response and call it
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/test-cache",
        status=200,
        body=json.dumps({"name": "foo"}),
    )
    client.get_repo("test/test-cache")

    # re-mock the repos request to a 404, should raise an exception if called directly
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/test-cache",
        status=404,
        body=json.dumps({"message": "Not found"}),
    )
    if use_cache:
        # No exception raised because the first response was cached
        client.get_repo("test/test-cache")
    else:
        # Exception raised because the repos endpoint was fetched again
        with pytest.raises(GithubAPIException, match="Not found"):
            client.get_repo("test/test-cache")


@pytest.mark.parametrize("state", ["open", "closed"])
def test_github_repo_get_pull_requests(httpretty, state):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    pull_requests = {
        "open": [
            {
                "url": "https://api.github.com/repos/test/foo/pulls/1",
                "id": 1,
                "state": "open",
                "title": "Open PR",
                "user": {"login": "testuser", "id": 123},
                "body": "",
                "created_at": "2021-08-16T04:11:31Z",
                "updated_at": None,
                "closed_at": None,
                "merged_at": None,
            }
        ],
        "closed": [
            {
                "url": "https://api.github.com/repos/test/foo/pulls/2",
                "id": 2,
                "state": "closed",
                "title": "Closed PR",
                "user": {"login": "testuser", "id": 123},
                "body": "",
                "created_at": "2021-08-01T10:00:00Z",
                "updated_at": None,
                "closed_at": "2021-08-12T09:11:00Z",
                "merged_at": None,
            }
        ],
    }
    # Mock the github requests
    httpretty.register_uri(
        httpretty.GET,
        f"https://api.github.com/repos/test/foo/pulls?state={state}&page=1&per_page=30",
        status=200,
        body=json.dumps(pull_requests[state]),
        match_querystring=True,
    )

    pulls = repo.get_pull_requests(state)
    assert pulls == pull_requests[state]


def test_github_repo_get_open_pull_request_count(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    pull_requests = [
        {
            "url": "https://api.github.com/repos/test/foo/pulls/1",
            "id": 1,
            "state": "open",
        },
        {
            "url": "https://api.github.com/repos/test/foo/pulls/2",
            "id": 2,
            "state": "open",
        },
    ]
    # Mock the github requests
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/pulls?state=open&page=1&per_page=30",
        status=200,
        body=json.dumps(pull_requests),
        match_querystring=True,
    )
    assert repo.open_pull_request_count == 2


def test_github_repo_get_branches(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    branches = [
        {
            "name": "test_branch",
            "commit": {
                "sha": "1aaa11aa111aaa1aaa1aaa11a1a01a1aa2a11111",
                "url": "https://api.github.com/repos/test/foo/commits/1aaa11aa111aaa1aaa1aaa11a1a01a1aa2a11111",
            },
            "protected": False,
        },
        {
            "name": "test_branch1",
            "commit": {
                "sha": "2aaa11aa111aaa1aaa1aaa11a1a01a1aa2a11111",
                "url": "https://api.github.com/repos/test/foo/commits/2aaa11aa111aaa1aaa1aaa11a1a01a1aa2a11111",
            },
            "protected": False,
        },
    ]
    # Mock the github requests
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/branches",
        status=200,
        body=json.dumps(branches),
        match_querystring=True,
    )
    assert repo.get_branches() == branches
    assert repo.branch_count == 2


def test_github_repo_get_multipage_pull_request_count(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    for i in range(1, 3):
        pull_requests = [
            {
                "url": f"https://api.github.com/repos/test/foo/pulls/{pr_num * i}",
                "id": pr_num * i,
                "state": "open",
            }
            for pr_num in range(1, 31)
        ]
        # Mock the github request
        httpretty.register_uri(
            httpretty.GET,
            f"https://api.github.com/repos/test/foo/pulls?state=open&page={i}&per_page=30",
            status=200,
            body=json.dumps(pull_requests),
            match_querystring=True,
        )
    last_page_pull_requests = [
        {
            "url": f"https://api.github.com/repos/test/foo/pulls/{pr_num * 3}",
            "id": pr_num * 3,
            "state": "open",
        }
        for pr_num in range(1, 11)
    ]
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/pulls?state=open&page=3&per_page=30",
        status=200,
        body=json.dumps(last_page_pull_requests),
        match_querystring=True,
    )
    assert repo.open_pull_request_count == 70


def test_github_repo_get_contents_single_file(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    str_content = """
        <html>
            <head>
                <style type="text/css">body {margin: 0;}</style>
                <style type="text/css">a {background-color: red;}</style>
                <script src="https://a-js-package.js"></script>
            </head>
            <body><p>foo</p></body>
        </html>
    """
    # Content retrieved from GitHub is base64-encoded, decoded to str for json
    b64_content = b64encode(bytes(str_content, encoding="utf-8")).decode()
    # Mock the github request
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder%2Ftest-file.html?ref=master",
        status=200,
        body=json.dumps(
            {
                "name": "test-file.html",
                "path": "test-folder/test-file.html",
                "sha": "abcd1234",
                "size": 1234,
                "encoding": "base64",
                "content": b64_content,
            }
        ),
    )
    # commits uri is also called, to get the last_updated date
    register_commits_uri(
        httpretty,
        owner="test",
        repo="foo",
        path="test-folder%2Ftest-file.html",
        sha="master",
        commit_dates="2021-03-01T10:00:00Z",
    )

    content_file = repo.get_contents("test-folder/test-file.html", ref="master")
    assert content_file.name == "test-file.html"
    # decoded content retrieves the original str contents
    assert content_file.decoded_content == str_content


def test_github_repo_get_last_updated(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    register_commits_uri(
        httpretty,
        owner="test",
        repo="foo",
        path="test-folder%2Ftest-file.html",
        sha="master",
        commit_dates=[
            "2021-03-01T10:00:00Z",
            "2021-02-14T10:00:00Z",
            "2021-02-01T10:00:00Z",
        ],
    )

    last_updated = repo.get_last_updated(
        path="test-folder/test-file.html", ref="master"
    )
    assert last_updated == date(2021, 3, 1)


@pytest.mark.parametrize(
    "status_code,body,expected_exception,expected_match",
    [
        (404, {"message": "Not found"}, GithubAPIException, "Not found"),
        (
            403,
            {"errors": [{"code": "other_code", "message": "An unexpected 403"}]},
            HTTPError,
            "Forbidden for url",
        ),
        (
            401,
            {"errors": [{"code": "other_code", "message": "An unexpected 403"}]},
            HTTPError,
            "Unauthorized for url",
        ),
        (
            403,
            {
                "unknown": [
                    {"code": "other_code", "message": "A 403 without an 'errors' key"}
                ]
            },
            GithubAPIException,
            "A 403 without an 'errors' key",
        ),
    ],
)
def test_github_repo_get_contents_exceptions(
    httpretty, status_code, body, expected_exception, expected_match
):
    """
    Test expected and unexpected exceptions from get_contents
    """
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    # Mock the github request
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder%2Ftest-file.html?ref=master",
        status=status_code,
        body=json.dumps(body),
    )
    with pytest.raises(expected_exception, match=expected_match):
        repo.get_contents("test-folder/test-file.html", ref="master")


def test_github_repo_get_contents_folder(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    # Mock the github request
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder?ref=master",
        status=200,
        body=json.dumps(
            [
                {
                    "name": "test-file1.html",
                    "path": "test-folder/test-file1.html",
                    "sha": "abcd1234",
                    "size": 1234,
                    "encoding": "base64",
                },
                {
                    "name": "test-file2.html",
                    "path": "test-folder/test-file2.html",
                    "sha": "abcd5678",
                    "size": 1234,
                    "encoding": "base64",
                },
            ]
        ),
    )
    contents = repo.get_contents("test-folder", ref="master")
    assert isinstance(contents, list)
    assert len(contents) == 2
    assert contents[0].name == "test-file1.html"
    assert contents[1].name == "test-file2.html"
    # decoded content returns None when the ContntFile was generated from a list of files
    # returned from github
    assert contents[0].decoded_content is None
    assert contents[1].decoded_content is None


def test_github_repo_get_contents_from_git_blob(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    str_content = """
        <html>
            <head>
                <style type="text/css">body {margin: 0;}</style>
                <style type="text/css">a {background-color: red;}</style>
                <script src="https://a-js-package.js"></script>
            </head>
            <body><p>foo</p></body>
        </html>
    """
    # Content retrieved from GitHub is base64-encoded, decoded to str for json
    b64_content = b64encode(bytes(str_content, encoding="utf-8")).decode()
    # Mock the github requests
    # get the parent folder contents
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder?ref=main",
        status=200,
        body=json.dumps(
            [
                {
                    "name": "test-file.html",
                    "path": "test-folder/test-file.html",
                    "sha": "abcd1234",
                    "size": 1234,
                    "encoding": "base64",
                },
            ]
        ),
    )
    # get the git blob
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/git/blobs/abcd1234",
        status=200,
        body=json.dumps(
            {
                "name": "test-file.html",
                "path": "test-folder/test-file.html",
                "sha": "abcd1234",
                "size": 1234,
                "encoding": "base64",
                "content": b64_content,
            }
        ),
    )
    # get the commits for last updated
    register_commits_uri(
        httpretty,
        owner="test",
        repo="foo",
        path="test-folder%2Ftest-file.html",
        sha="main",
        commit_dates="2021-03-01T10:00:00Z",
    )
    content_file = repo.get_contents(
        "test-folder/test-file.html", "main", from_git_blob=True
    )
    assert content_file.name == "test-file.html"
    # decoded content retrieves the original str contents
    assert content_file.decoded_content == str_content


def test_github_repo_get_contents_too_large_file(httpretty):
    """
    Test get_contents with a too-large file resorts to fetching content from the git blob
    """
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    str_content = """
        <html>
            <head>
                <style type="text/css">body {margin: 0;}</style>
                <style type="text/css">a {background-color: red;}</style>
                <script src="https://a-js-package.js"></script>
            </head>
            <body><p>foo</p></body>
        </html>
    """
    # Content retrieved from GitHub is base64-encoded, decoded to str for json
    b64_content = b64encode(bytes(str_content, encoding="utf-8")).decode()

    # Mock the github requests
    # First tries the contents endpoint and gets a 403
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder%2Ftest-file.html?ref=main",
        status=403,
        body=json.dumps(
            {"errors": [{"code": "too_large", "message": "File was too large"}]}
        ),
    )
    # gets the parent folder contents
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/contents/test-folder?ref=main",
        status=200,
        body=json.dumps(
            [
                {
                    "name": "test-file.html",
                    "path": "test-folder/test-file.html",
                    "sha": "abcd1234",
                    "size": 1234,
                    "encoding": "base64",
                },
            ]
        ),
    )
    # then gets the git blob
    httpretty.register_uri(
        httpretty.GET,
        "https://api.github.com/repos/test/foo/git/blobs/abcd1234",
        status=200,
        body=json.dumps(
            {
                "name": "test-file.html",
                "path": "test-folder/test-file.html",
                "sha": "abcd1234",
                "size": 1234,
                "encoding": "base64",
                "content": b64_content,
            }
        ),
    )
    # get the commits for last updated
    register_commits_uri(
        httpretty,
        owner="test",
        repo="foo",
        path="test-folder%2Ftest-file.html",
        sha="main",
        commit_dates="2021-03-01T10:00:00Z",
    )
    content_file = repo.get_contents("test-folder/test-file.html", ref="main")
    assert content_file.decoded_content == str_content
    assert content_file.last_updated == date(2021, 3, 1)


def test_github_repo_get_url():
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    assert repo._url is None
    assert repo.url == "https://github.com/test/foo"
    assert repo._url == repo.url


def test_github_repo_override_url():
    # Overriding the url allows tests to
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    assert repo.url == "https://github.com/test/foo"


@pytest.mark.django_db
def test_clear_cache(reset_environment_after_test):
    # make sure we start with a fresh cache
    remove_cache_file_if_exists()
    client = GithubClient(use_cache=True)
    # no github requests have been made, so cache is currently clear
    assert list(client.session.cache.urls) == []

    repo = client.get_repo("opensafely/output-explorer-test-repo")
    repo.get_contents("test-outputs/output.html", "master")

    # 3 calls made, to get repo, get contents and get commits
    assert len(list(client.session.cache.urls)) == 3
    # make another request using this cache session
    client.session.get("https://www.opensafely.org/")
    assert len(list(client.session.cache.urls)) == 4
    # Clearing the cache only clears urls related to this report
    repo.clear_cache()
    assert list(client.session.cache.urls) == ["https://www.opensafely.org/"]
