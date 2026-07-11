# Contributing Guidelines

Thank you for contributing to the CYSD ERP Dashboard! Follow these guidelines to set up your environment, write quality code, and make contributions.

---

## 1. Setup Dev Environment

1. **Activate Virtual Environment**:
   ```bash
   py -m venv .venv
   .venv\Scripts\activate
   ```
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```
3. **Configure Environment**:
   Make sure you copy `.env.example` to `.env` and set up the local development database.
4. **Local Subdomain Testing**:
   Add mappings in your hosts file (`C:\Windows\System32\drivers\etc\hosts`) to test multi-tenancy:
   ```text
   127.0.0.1 cysd.localhost
   127.0.0.1 rasayam.localhost
   ```

---

## 2. Coding Standards

We use **Ruff** for linting and formatting. Ensure that your changes are formatted correctly:

1. **Run Linter Checks**:
   ```bash
   py -m ruff check .
   ```
2. **Auto-fix Lint Warnings**:
   ```bash
   py -m ruff check --fix .
   ```

---

## 3. Writing and Running Tests

Every model validator, custom model method, and RBAC security rule should be thoroughly covered by unit tests.

1. **Run the Test Suite**:
   ```bash
   py manage.py test
   ```
2. **Target High Coverage**:
   Ensure that any new fields or endpoint permissions are validated by corresponding tests in `tracker/tests.py`.

---

## 4. Git Workflow

1. Work incrementally on your branch.
2. Commit each completed numbered item with a clear commit message.
3. Verify that the test suite and Ruff pass locally before opening a pull request.
