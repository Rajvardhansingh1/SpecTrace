# Petstore Guide

## Listing pets
Call `GET /pets` to list all pets. Each item is a `Pet`.

## Fetching a pet
Call `GET /pets/{petId}` to fetch one pet.

REQ-001: Clients MUST treat the `Pet` id as an opaque string.

```json
{"id": "p-1", "name": "Rex", "tag": "dog"}
```

## Owners
Call `GET /owners` to list owners.
