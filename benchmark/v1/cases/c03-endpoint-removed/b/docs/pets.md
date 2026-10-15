# Pets

## Removing a pet
Call `DELETE /pets/{petId}` to remove a pet. The call returns 204.

REQ-010: Clients MUST call `DELETE /pets/{petId}` before archiving a pet.

## Reading a pet
Call `GET /pets/{petId}` to read a pet.
