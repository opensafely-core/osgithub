# github-api-cache

A thin wrapper around the GitHub API, with cached requests by default.

## Environment
Set the following environment variables:
 - `GITHUB_USER_AGENT` - a string to identify your application
 - `GITHUB_TOKEN` - optional; default token to use.
 - `REQUESTS_CACHE_NAME` - optional, defaults to "http_cache"

## Usage

```
from github_api_cache import GithubClient

# use the default token, if one is set in the envrionment.
client = GithubClient()

# get a repo (returns a GithubRepo)
repo = client.get_repo("opensafely-core/github-api-cache")

# get a list of branches
repo.get_branches()

# get a list of open pull requests
repo.get_pull_requests()

# get the contents of the `github_api_cache` directory on branch `main`
# returns a list of GithubContentFile objects
repo.get_contents("github_api_cache", "main")

# get a single file; returns a GithubContentFile
repo.get_contents("github_api_cache/__init__.py", "main")
```

### Caching
All requests are cached by default, using a sqlite backend.

To specify other cache options:

Disable caching:
```
client = GithubClient(use_cache=False)
OR
client = GithubClient(expire_after=0)
```

Set a global expiry for the session (never expires by default):
```
# expire all cached requests after 300s
client = GithubClient(expire_after=300)
```

Set expiry on specific url patterns (falls back to `expire_after` if no match found)
```
urls_expire_after = {
    '*/pulls': 60,  # expire requests to get pull requests after 60 secs
    '*/branches': 60 * 5, # expire requests to get branches after 5 mins
    '*/commits': 30,  # expire requests to get commits after 30 secs
}
client = GithubClient(urls_expire_after=urls_expire_after)
```

## Developer docs

Please see the [additional information](DEVELOPERS.md).
