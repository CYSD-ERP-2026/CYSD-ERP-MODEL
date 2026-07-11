# System Architecture

This document provides a comprehensive overview of the design patterns, security isolation, and workflows implemented in the CYSD ERP Dashboard.

---

## 1. Multi-Tenant Architecture

The system is built as a multi-tenant Software as a Service (SaaS) application using a **subdomain-based tenant isolation model**.

### Flow of Tenant Resolution
```
Request to [tenant].localhost:8000
       │
       ▼
TenantMiddleware (resolves subdomain)
       │
       ├─► NotFound (404) if Enterprise does not exist
       │
       ▼
Attaches Enterprise instance to request.tenant
       │
       ▼
Django Views / Queries (Scoped to request.tenant)
```

1. **Subdomain Detection**: The custom [TenantMiddleware](file:///C:/Users/debab/OneDrive/Desktop/cysd-erp/tracker/middleware.py) parses the request hostname to extract the leftmost subdomain (e.g. `cysd` from `cysd.localhost`).
2. **Tenant Mapping**: It queries the [Enterprise](file:///C:/Users/debab/OneDrive/Desktop/cysd-erp/tracker/models.py) database table to find a matching tenant:
   * If not found, a `404 Not Found` response is raised.
   * If found, the resolved `Enterprise` instance is attached to `request.tenant`.
3. **Database-Level Isolation**: Every multi-tenant model (e.g., `Domain`, `Employee`, `Meeting`, `Project`, `Task`, `TaskChecklist`) contains a foreign key to the `Enterprise` model. All queries in the view layer are explicitly filtered by `enterprise=request.tenant`.
4. **Boundary Checks**: If an authenticated user attempts to access a subdomain different from the one designated in their profile, they are automatically logged out with an authorization error.

---

## 2. Role-Based Access Control (RBAC)

Access permissions are enforced dynamically based on the employee's role within the enterprise. The roles supported by the system are:

* **Founder (Admin)**: Full read/write access across all system entities. Can assign tasks to any employee.
* **HR**: Full read/write access to employees and domains. Can view analytics. Agenda/minutes/action points of meetings are masked/redacted for confidentiality.
* **Supervisor**: Read/write access to domains, meetings, and projects. Can assign task checklist items and verify submissions **only** for employees who directly report to them.
* **Employee / Intern / Volunteer**: Read-only access to their primary domain data. Access to a personal "My Tasks & Deliverables" dashboard where they can submit completed tasks/checklists.

### RBAC Permission Matrix

| Model / Action | Founder | HR | Supervisor | Employee / Intern / Volunteer |
| :--- | :--- | :--- | :--- | :--- |
| **Manage Enterprise settings** | Yes | Yes | No | No |
| **Create/Edit Domains** | Yes | Yes | Yes | No |
| **Create/Edit Employees** | Yes | Yes | No | No |
| **View Confidential Meetings** | Yes | No (Masked) | Yes | Yes (Domain-scoped) |
| **Assign Task Checklist Items** | Anyone | Anyone | Subordinates Only | No |
| **Resolve/Approve Checklists** | Anyone | Anyone | Subordinates Only | No |
| **Submit Checklists for Review** | No | No | No | Assigned User Only |

---

## 3. Task Checklist State Machine

The verification workflow for custom task checklists implements a robust 3-phase transition lifecycle to enforce accountability.

```
       [Supervisor Assigns Checklist]
                     │
                     ▼
              ┌─────────────┐
              │   PENDING   │ ◄──────────────────────────┐
              └──────┬──────┘                            │
                     │                                   │
         [Employee marks as Done]                [Supervisor Rejects]
                     │                                   │
                     ▼                                   │
       ┌───────────────────────────┐                     │
       │   AWAITING_VERIFICATION   ├─────────────────────┘
       └─────────────┬─────────────┘
                     │
            [Supervisor Approves]
                     │
                     ▼
              ┌─────────────┐
              │  COMPLETED  │  ──► (Triggers atomic EmployeeStats refresh)
              └─────────────┘
```

### Transition Rules
1. **PENDING**: The default state on task assignment.
2. **AWAITING_VERIFICATION**: The employee marks the checkbox on their personal dashboard. This records `submitted_at` and sends the item to the supervisor's Verification Center.
3. **COMPLETED**: The supervisor reviews and approves the submission. This transition automatically triggers the `EmployeeStats` recalculation signal.
4. **Rejection (Return to PENDING)**: If the supervisor rejects the submission, they must provide feedback. The state returns to `PENDING` to allow revision, clearing the previous timestamps.
