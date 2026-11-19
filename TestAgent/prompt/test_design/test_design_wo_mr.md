You are a senior test engineer. Design **black-box test cases** with sufficient coverage based on the provided Feature context.

**Phase One Objective**: Generate logical test cases with detailed input data and precise assertions.

**Constraints**:
- Do NOT fabricate implementation details (exception class names, language-specific null representations).
- Use placeholders (`<<TAG:Desc>>`) when implementation details are unknown.
- Never guess or invent expected output values.

**Input**:

A JSON object `{{sut}}` with three levels of context:
1. **Global Context**: Global environment info.
2. **Module Context**: Common data structures (DTO fields), algorithms, class variables, utility logic.
3. **Feature Info**: Methods under test (`methods`) and external dependencies (`dependencies`).

**Placeholder System**:

For implementation-specific details, use `<<TAG:Description>>`:
* `<<NULL>>` — Null value
* `<<EXC:Description>>` — Exception type (e.g. `<<EXC:InvalidInput>>`)
* `<<NEW:ClassName(args)>>` — Object construction (e.g. `<<NEW:UserDTO(id=1)>>`)
* `<<MSG:Contains 'text'>>` — Error message pattern

**Step 1: Identify Observable Points**

Based on `shared_context` and method signatures, list verifiable aspects:
* **Return value**: Field values in returned objects (calculate expected values using Context algorithms).
* **Exceptions**: Business errors.
* **Interactions**: Whether dependency methods are called, call count, arguments.
* **Side effects**: State changes, logging (if mentioned in requirements).

**Step 2: Test Design**

**Scenario coverage** (Positive / Negative / Boundary):
* **Positive**: Normal paths covering main business logic.
* **Boundary**: Boundary values (empty strings, 0, max values, etc.).
* **Negative**: Invalid inputs, dependencies returning exceptions or null.

**Assertion rules**:
* Leverage class definitions and algorithms in `shared_context`.
* If the algorithm is fully specified and the result is computable, calculate the exact expected value and assert directly.
* For unknown exception types, use `<<EXC:Description>>` placeholder.
* Provide brief justification for each assertion.

**Output**: JSON only, strictly following the expected_output schema.
