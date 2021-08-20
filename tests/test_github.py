import json
from base64 import b64encode
from datetime import date
from os import environ

import pytest
from furl import furl
from requests.exceptions import HTTPError

from osgithub import GithubAPIException, GithubClient, GithubRepo

from .conftest import remove_cache_file_if_exists


def register_uri(httpretty, path, queryparams=None, status=200, body=None):
    url = furl("https://api.github.com")
    url.path.segments += [*path.split("/")]
    if queryparams:
        url.add(queryparams)
    httpretty.register_uri(
        httpretty.GET,
        url.url,
        status=status,
        body=json.dumps(body or ""),
        match_querystring=True,
    )


def test_github_client_get_repo(httpretty):
    # Mock the github request
    register_uri(httpretty, "repos/test/foo", body={"name": "foo"})
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
    register_uri(httpretty, "repos/test/bar", status=404, body={"message": "Not found"})
    client = GithubClient()
    with pytest.raises(GithubAPIException, match="Not found"):
        client.get_repo("test/bar")


@pytest.mark.parametrize("use_cache", [True, False])
def test_github_client_get_repo_with_cache(httpretty, use_cache):
    client = GithubClient(use_cache=use_cache)

    # set up mock request with valid response and call it
    register_uri(httpretty, "repos/test/test-cache", body={"name": "foo"})
    client.get_repo("test/test-cache")

    # re-mock the repos request to a 404, should raise an exception if called directly
    register_uri(
        httpretty, "repos/test/test-cache", status=404, body={"message": "Not found"}
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
    register_uri(
        httpretty,
        "repos/test/foo/pulls",
        queryparams=dict(state=state, page=1, per_page=30),
        body=pull_requests[state],
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
    register_uri(
        httpretty,
        "repos/test/foo/pulls",
        queryparams=dict(state="open", page=1, per_page=30),
        body=pull_requests,
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
    register_uri(httpretty, "repos/test/foo/branches", body=branches)
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
        register_uri(
            httpretty,
            "repos/test/foo/pulls",
            queryparams=dict(state="open", page=i, per_page=30),
            body=pull_requests,
        )
    last_page_pull_requests = [
        {
            "url": f"https://api.github.com/repos/test/foo/pulls/{pr_num * 3}",
            "id": pr_num * 3,
            "state": "open",
        }
        for pr_num in range(1, 11)
    ]
    register_uri(
        httpretty,
        "repos/test/foo/pulls",
        queryparams=dict(state="open", page=3, per_page=30),
        body=last_page_pull_requests,
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
    reponse_json = {
        "name": "test-file.html",
        "path": "test-folder/test-file.html",
        "sha": "abcd1234",
        "size": 1234,
        "encoding": "base64",
        "content": b64_content,
    }
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder/test-file.html",
        queryparams=dict(ref="main"),
        body=reponse_json,
    )

    commits_response = [{"commit": {"committer": {"date": "2021-03-01T10:00:00Z"}}}]
    register_uri(
        httpretty,
        "repos/test/foo/commits",
        queryparams=dict(sha="main", path="test-folder/test-file.html", per_page=1),
        body=commits_response,
    )

    content_file = repo.get_contents("test-folder/test-file.html", ref="main")
    assert content_file.name == "test-file.html"
    # decoded content retrieves the original str contents
    assert content_file.decoded_content == str_content

    # get contents with content fetch type
    content_file, fetch_type = repo.get_contents(
        "test-folder/test-file.html", ref="main", return_fetch_type=True
    )
    assert content_file.name == "test-file.html"
    assert fetch_type == "contents"


def test_github_repo_get_last_updated(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    commit_dates = [
        "2021-03-01T10:00:00Z",
        "2021-02-14T10:00:00Z",
        "2021-02-01T10:00:00Z",
    ]
    commits_response = [
        {"commit": {"committer": {"date": commit_date}}} for commit_date in commit_dates
    ]
    register_uri(
        httpretty,
        "repos/test/foo/commits",
        queryparams=dict(sha="main", path="test-folder/test-file.html", per_page=1),
        body=commits_response,
    )

    last_updated = repo.get_last_updated(path="test-folder/test-file.html", ref="main")
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
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder/test-file.html",
        queryparams=dict(ref="main"),
        status=status_code,
        body=body,
    )
    with pytest.raises(expected_exception, match=expected_match):
        repo.get_contents("test-folder/test-file.html", ref="main")


@pytest.mark.parametrize(
    "filepath,expected_filename",
    [
        ("test-folder/test-file.html", "test-file.html"),
        ("test-folder/test-file1.html", "test-file1.html"),
        ("test-folder/test-file2.html", None),
    ],
)
def test_github_repo_matching_file_from_parent_contents(
    httpretty, filepath, expected_filename
):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    # Mock the github requests
    # get the parent folder contents
    response_json = [
        {
            "name": "test-file.html",
            "path": "test-folder/test-file.html",
            "sha": "abcd1234",
            "size": 1234,
            "encoding": "base64",
        },
        {
            "name": "test-file1.html",
            "path": "test-folder/test-file1.html",
            "sha": "abcd2345",
            "size": 1234,
            "encoding": "base64",
        },
    ]
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder",
        queryparams=dict(ref="main"),
        body=response_json,
    )

    matching_file = repo.matching_file_from_parent_contents(filepath, "main")
    if expected_filename is None:
        assert matching_file is None
    else:
        assert matching_file.name == expected_filename


def test_github_repo_get_contents_folder(httpretty):
    repo = GithubRepo(client=GithubClient(use_cache=False), owner="test", name="foo")
    # Mock the github request
    response_json = [
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
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder",
        queryparams=dict(ref="main"),
        body=response_json,
    )
    contents = repo.get_contents("test-folder", ref="main")
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
    response_json = [
        {
            "name": "test-file.html",
            "path": "test-folder/test-file.html",
            "sha": "abcd1234",
            "size": 1234,
            "encoding": "base64",
        },
    ]
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder",
        queryparams=dict(ref="main"),
        body=response_json,
    )

    # get the git blob
    response_json = {
        "name": "test-file.html",
        "path": "test-folder/test-file.html",
        "sha": "abcd1234",
        "size": 1234,
        "encoding": "base64",
        "content": b64_content,
    }
    register_uri(httpretty, "repos/test/foo/git/blobs/abcd1234", body=response_json)

    # get the commits for last updated
    commits_response = [{"commit": {"committer": {"date": "2021-03-01T10:00:00Z"}}}]
    register_uri(
        httpretty,
        "repos/test/foo/commits",
        queryparams=dict(sha="main", path="test-folder/test-file.html", per_page=1),
        body=commits_response,
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
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder/test-file.html",
        status=403,
        queryparams=dict(ref="main"),
        body={"errors": [{"code": "too_large", "message": "File was too large"}]},
    )

    # gets the parent folder contents
    register_uri(
        httpretty,
        "repos/test/foo/contents/test-folder",
        status=200,
        queryparams=dict(ref="main"),
        body=[
            {
                "name": "test-file.html",
                "path": "test-folder/test-file.html",
                "sha": "abcd1234",
                "size": 1234,
                "encoding": "base64",
            },
        ],
    )

    # then gets the git blob
    register_uri(
        httpretty,
        "repos/test/foo/git/blobs/abcd1234",
        status=200,
        body={
            "name": "test-file.html",
            "path": "test-folder/test-file.html",
            "sha": "abcd1234",
            "size": 1234,
            "encoding": "base64",
            "content": b64_content,
        },
    )

    # get the commits for last updated
    commits_response = [{"commit": {"committer": {"date": "2021-03-01T10:00:00Z"}}}]
    register_uri(
        httpretty,
        "repos/test/foo/commits",
        queryparams=dict(sha="main", path="test-folder/test-file.html", per_page=1),
        body=commits_response,
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


def test_clear_cache(httpretty, reset_environment_after_test):
    # mock the requests
    register_uri(httpretty, "repos/test/foo", body={"name": "foo"})
    httpretty.register_uri(httpretty.GET, "https://www.test.com/", status=200)

    # make sure we start with a fresh cache
    remove_cache_file_if_exists()
    client = GithubClient(use_cache=True)
    # no github requests have been made, so cache is currently clear
    assert list(client.session.cache.urls) == []

    # A real repo
    repo = client.get_repo("test/foo")

    # 1 call made, to get contents
    assert len(list(client.session.cache.urls)) == 1
    # make another request using this cache session
    client.session.get("https://www.test.com/")
    assert len(list(client.session.cache.urls)) == 2
    # Clearing the cache only clears urls related to this report
    repo.clear_cache()
    assert list(client.session.cache.urls) == ["https://www.test.com/"]


@pytest.mark.integration
def test_integration(reset_environment_after_test):
    """Test repo methods with a real github repo"""
    # make sure we start with a fresh cache
    remove_cache_file_if_exists()
    client = GithubClient(use_cache=True)
    # Set up a real repo
    repo = client.get_repo("opensafely/output-explorer-test-repo")

    # Fetch a known folder
    contents = repo.get_contents("test-outputs", ref="master")
    assert len(contents) == 4
    assert sorted([contentfile.name for contentfile in contents]) == [
        "output.html",
        "sro-measures.html",
        "vaccine-coverage-new.html",
        "vaccine-coverage-original.html",
    ]

    # Fetch a file
    contents, fetch_type = repo.get_contents(
        "test-outputs/output.html", ref="master", return_fetch_type=True
    )
    assert contents.name == "output.html"
    assert fetch_type == "contents"

    # Fetch a non-existent file
    with pytest.raises(GithubAPIException):
        repo.get_contents("test-outputs/output-unknown.html", ref="master")

    # Fetch a non-existent branch
    with pytest.raises(GithubAPIException):
        repo.get_contents("test-outputs/output.html", ref="foo")

    # Fetch README
    readme = repo.get_readme(tag="master")
    assert (
        readme
        == "# output-explorer Tests\n\nThis is a test repo for use by output-explorer's tests.\n\n"
    )

    # Fetch details
    details = repo.get_repo_details()
    assert details == {
        "name": "output-explorer-test-repo",
        "about": "A test repo for output-explorer's tests",
    }

    # Fetch tags
    tagged_sha = "7a6f60e8e74b9c93a9c6322b3151ee437fa4be61"
    tags = repo.get_tags()
    assert len(tags) >= 1
    assert {"tag_name": "test-tag", "sha": tagged_sha} in tags

    # get commit details
    commit = repo.get_commit(sha=tagged_sha)
    assert commit == {"author": "Ben Butler-Cole", "date": "2021-06-02T10:52:37Z"}
