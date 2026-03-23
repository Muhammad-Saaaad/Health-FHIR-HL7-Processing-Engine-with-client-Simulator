
# Query Parameters vs Query Paths in APIs

## Definitions

**Query Parameters**: Key-value pairs appended to a URL after a `?` symbol, separated by `&`.
```
GET /api/patients?name=John&age=30
```

**Query Paths**: Path segments that are part of the URL structure itself, typically enclosed in curly braces or represented as segments.
```
GET /api/patients/{id}/records
```

## How to Call Them

- **Query Parameters**: `?key=value&key2=value2`
- **Query Paths**: `/resource/{identifier}/subresource`

## API Design

### Query Parameters API
```
GET /api/patients?firstName=John&lastName=Doe&status=active
GET /api/medications?code=12345&type=prescription
```

### Query Paths API
```
GET /api/patients/{patientId}/appointments
GET /api/encounters/{encounterId}/observations
```

## Key Differences

| Aspect | Query Parameters | Query Paths |
|--------|------------------|-------------|
| **Placement** | After `?` in query string | Part of URL structure |
| **Mandatory** | Optional | Required for resource identification |
| **Caching** | Can be problematic | Better for caching |
| **Readability** | Good for filters/options | Good for hierarchies |
| **RESTful** | Filters, search, pagination | Resource hierarchy |

## When to Use

**Query Paths**: When you need to identify a specific resource or navigate a hierarchy.
- `/fhir/Patient/{id}`
- `/fhir/Patient/{id}/Observation`

**Query Parameters**: When filtering, searching, or applying optional conditions.
- `/fhir/Patient?name=John&birthdate=1990`
- `/fhir/Medication?code=aspirin&status=active`
