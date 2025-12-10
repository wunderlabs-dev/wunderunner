# Contributing to wunderunner

Thank you for your interest in contributing to wunderunner! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker (for testing generated configurations)

### Development Setup

```bash
# Clone the repository
git clone https://github.com/wunderlabs-dev/wunderunner.git
cd wunderunner

# Install dependencies
make dev

# Run tests
make test

# Run linter
make lint
```

## How to Contribute

### Reporting Bugs

Before submitting a bug report:

1. Check existing [issues](https://github.com/wunderlabs-dev/wunderunner/issues) to avoid duplicates
2. Use the latest version to confirm the bug still exists

When reporting, include:

- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Python version and OS
- Relevant logs or error messages

### Suggesting Features

Feature requests are welcome! Please:

1. Check existing issues for similar suggestions
2. Describe the problem your feature would solve
3. Explain your proposed solution
4. Consider alternatives you've thought about

### Pull Requests

1. **Fork and branch**: Create a feature branch from `main`
2. **Write tests**: New features need tests; bug fixes should include regression tests
3. **Follow style**: Run `make lint` and `make format` before committing
4. **Write clear commits**: Use descriptive commit messages
5. **Update docs**: If your change affects usage, update the README

#### PR Checklist

- [ ] Tests pass (`make test`)
- [ ] Linter passes (`make lint`)
- [ ] Code is formatted (`make format`)
- [ ] Commit messages are clear
- [ ] Documentation updated if needed

## Code Style

- Follow existing code patterns in the repository
- Use type hints for all function signatures
- Keep functions focused and small
- Prefer simple solutions over clever ones

## Testing

```bash
# Run all tests
make test

# Run specific test file
uv run pytest tests/test_foo.py -v

# Run specific test
uv run pytest tests/test_foo.py::test_specific -v
```

## Questions?

- Open a [discussion](https://github.com/wunderlabs-dev/wunderunner/discussions) for general questions
- Open an [issue](https://github.com/wunderlabs-dev/wunderunner/issues) for bugs or feature requests

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
