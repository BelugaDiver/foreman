# Non-GET Endpoint Parameter Standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize non-GET endpoints to explicitly use `Body()` for payload parameters, ensuring a clear separation from Path parameters.

**Architecture:** Use FastAPI's `Body(...)` marker in endpoint function signatures for all non-resource-ID parameters in `POST`, `PUT`, `PATCH`, and `DELETE` methods.

**Tech Stack:** FastAPI, Pydantic, Python 3.14.

---

### Task 1: Update Generations API

**Files:**
- Modify: `foreman/api/v1/endpoints/generations.py`
- Test: `tests/test_generations_api.py`

- [ ] **Step 1: Import Body from fastapi**
- [ ] **Step 2: Update `update_generation` (PATCH) to use `Body()`**
- [ ] **Step 3: Run existing tests to ensure no regressions**
Run: `pytest tests/test_generations_api.py -v`
- [ ] **Step 4: Commit**
```bash
git add foreman/api/v1/endpoints/generations.py
git commit -m "refactor(api): use explicit Body for generation update"
```

---

### Task 2: Update Images API

**Files:**
- Modify: `foreman/api/v1/endpoints/images.py`
- Test: `tests/test_images.py`

- [ ] **Step 1: Import Body from fastapi**
- [ ] **Step 2: Update `create_upload_intent` (POST) to use `Body()`**
- [ ] **Step 3: Run existing tests to ensure no regressions**
Run: `pytest tests/test_images.py -v`
- [ ] **Step 4: Commit**
```bash
git add foreman/api/v1/endpoints/images.py
git commit -m "refactor(api): use explicit Body for image upload intent"
```

---

### Task 3: Update Projects API

**Files:**
- Modify: `foreman/api/v1/endpoints/projects.py`
- Test: `tests/test_projects.py`
- Test: `tests/test_project_generations_api.py`

- [ ] **Step 1: Import Body from fastapi**
- [ ] **Step 2: Update `create_project` (POST) to use `Body()`**
- [ ] **Step 3: Update `create_generation` (POST) to use `Body()`**
- [ ] **Step 4: Update `update_project` (PATCH) to use `Body()`**
- [ ] **Step 5: Run existing tests to ensure no regressions**
Run: `pytest tests/test_projects.py tests/test_project_generations_api.py -v`
- [ ] **Step 4: Commit**
```bash
git add foreman/api/v1/endpoints/projects.py
git commit -m "refactor(api): use explicit Body for project and generation endpoints"
```

---

### Task 4: Update Users API

**Files:**
- Modify: `foreman/api/v1/endpoints/users.py`
- Test: `tests/test_users.py`

- [ ] **Step 1: Import Body from fastapi**
- [ ] **Step 2: Update `create_user` (POST) to use `Body()`**
- [ ] **Step 3: Update `update_user_me` (PATCH) to use `Body()`**
- [ ] **Step 4: Run existing tests to ensure no regressions**
Run: `pytest tests/test_users.py -v`
- [ ] **Step 5: Commit**
```bash
git add foreman/api/v1/endpoints/users.py
git commit -m "refactor(api): use explicit Body for user endpoints"
```
