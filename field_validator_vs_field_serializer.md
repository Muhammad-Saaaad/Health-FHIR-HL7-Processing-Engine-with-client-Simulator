# field_validator vs field_serializer

`field_validator` and `field_serializer` are Pydantic v2 hooks for one field.

## 1) field_validator

1. Runs during input validation (model creation).
2. Used to clean, convert, or check incoming values.
3. Example in your schema: convert `"2026-04-12"` string into a `date` object before normal type validation.

## 2) field_serializer

1. Runs when exporting model data (like API response JSON).
2. Used to control how a field is rendered in output.
3. Example in your schema: convert `date(2026, 4, 12)` into `"April 12, 2026"`.

## In short

1. `field_validator` = input side
2. `field_serializer` = output side

## Your last_visit flow

1. Client sends `"2026-04-12"` -> validator parses it to `date`.
2. API returns model -> serializer formats it as `"April 12, 2026"`.
