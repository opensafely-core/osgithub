# Notes for developers

## System requirements

### just >=0.9.9

```sh
# macOS
brew install just

# Linux
# Install from https://github.com/casey/just/releases

# Add completion for your shell. E.g. for bash:
source <(just --completions bash)

# Show all available commands
just #  shortcut for just --list
```


## Local development environment


Set up a local development environment with:
```
just dev_setup
```

## Tests
Run the tests with:
```
just test <args>
```

Run only the non-integration tests (that don't call GitHub):
```
just test '-m "not integration"'
```
