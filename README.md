# osgithub

A thin wrapper around the GitHub API.

## Environment
Set the following environment variables:
 - `GITHUB_USER_AGENT` - a string to identify your application
 - `GITHUB_TOKEN` - optional; default token to use.
 - `REQUESTS_CACHE_NAME` - optional, defaults to "http_cache"

## Usage

### Create a client
```
from github_api_cache import GithubClient
# Use the default token, if one is set in the environment.
client = GithubClient()
```

### get a repo (returns a GithubRepo)
```
repo = client.get_repo("opensafely-core/osgithub")
```

#### get a list of branches
```
repo.get_branches()
```
And branch count:
```
repo.branch_count
```

#### get a list of pull requests
Provide a `page` argument to get more pages than just the first one (30 result are returned per page).
```
repo.get_pull_requests(page=1)
```

By default, this fetches open PRs only.  To retrieve other states, pass `state="closed"` or `state="open"`

Pull request counts:
```
repo.pull_request_count
repo.open_pull_request_count
```

#### get the contents of the `osgithub` directory on branch `main`
```
# returns a list of GithubContentFile objects
repo.get_contents("osgithub", "main")
```

#### get a single file; returns a GithubContentFile
```
repo.get_contents("osgithub/__init__.py", "main")
```

#### get_commits_for_file(self, path, ref, number_of_commits=1):
Returns a list of commits, just the last one by default
```
repo.get_commits_for_file("osgithub", "main")
```
To return more commits:
```
repo.get_commits_for_file("osgithub", "main", number_of_commits=10)
```

Get details for a single commit by sha - returns author and date of the commit
```
repo.get_commit("7a6f60e8e74b9c93a9c6322b3151ee437fa4be61")
```


#### Repo information

Fetch the HTML from the README.md of repo:
```
repo.get_readme(tag="main")
```

Fetch the About and Name of the repo:
```
repo.get_details()
```

Fetch tags with name and sha:
```
repo.get_tags()
```


### Caching
Requests can optionally be cached, using a sqlite backend.

To use caching:
```
client = GithubClient(use_cache=True)
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

#### Clear the cache for this repo
```
repo.clear_cache()
```

## Developer docs

Please see the [additional information](DEVELOPERS.md).
