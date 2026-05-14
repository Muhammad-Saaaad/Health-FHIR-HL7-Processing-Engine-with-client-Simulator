from pydantic import BaseModel

class MiniTestCreate(BaseModel):
    """Schema for a single mini-test result input."""
    test_name: str
    normal_range: str
    units: str
    result_value: str

class CompleteTestResultCreate(BaseModel):
    user_id: int
    test_req_id: int
    lab_id: int
    description: str| None = None
    mini_tests: list[MiniTestCreate] # Nested list of mini-tests

class MiniTestOut(BaseModel):
    """Schema for returning a single mini-test result."""
    mini_test_id: int
    test_name: str
    normal_range: str
    units: str
    result_value: str
    
    model_config = {"from_attributes":True}

class TestResultOut(BaseModel):
    result_id: int
    user_id: int
    test_req_id: int
    description: str | None
    mini_test_results: list[MiniTestOut] | None = None
    
    model_config = {"from_attributes":True}