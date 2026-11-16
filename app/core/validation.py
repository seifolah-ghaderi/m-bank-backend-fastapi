from app.core.errors import DomainError


def validated_changes(body, required):
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(key) is None for key in required if key in changes):
        raise DomainError(422, "invalid_field")
    return changes
