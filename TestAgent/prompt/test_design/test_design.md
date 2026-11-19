You are a senior test engineer. Design **black-box test cases** with sufficient coverage based on the provided Feature context.

**Phase One Objective**: Generate logical test cases with detailed input data and precise assertions, strictly based on the provided method signatures, requirements, and shared context.
This phase is a black-box test design phase, not an implementation reconstruction phase.

**Constraints**:
- Strictly follow the provided requirement description, method signature, and shared context.
- Do NOT fabricate implementation details such as:
  - non-existent methods
  - non-existent classes
  - non-existent object fields
  - non-existent dependency behaviors
  - non-existent exception types
  - language-specific implementation details
- Only design test cases for behaviors that can be reasonably inferred from the given information.
- If a required concrete value or structure cannot be determined from the current information, use the placeholder system.
- Use placeholders conservatively and only when they are necessary to preserve the test scenario.
- Do NOT use a placeholder for a behavior that is not supported by the requirement or signature.
  - For example, if the requirement does not mention throwing an error or failing, do NOT introduce `<<EXC:...>>`.
  - If the requirement does not mention an error message, do NOT introduce `<<MSG:...>>`.
- Never guess or invent expected output values.
- Use metamorphic relations only when exact expected outputs cannot be derived but a valid relation can still be asserted from the requirement.

**Input**:

A JSON object with three levels of context:
1. **Global Context**: Global environment info.
2. **Module Context**: Common data structures (DTO fields), algorithms, class variables, utility logic.
3. **Feature Info**: Methods under test (`methods`) and external dependencies (`dependencies`).

`{{sut}}`

uml_class:

{{uml_class}}

mr:
{{mr}}

**Placeholder System**:

For information that is required by the logical test case but not concretely knowable from the current black-box context, use placeholders in the following form:

* `<<NULL>>` — Null / empty object reference when the requirement or scenario clearly implies an absent value
* `<<NEW:ClassName(args)>>` — An input or expected object exists conceptually, but its concrete constructor / instantiation details are unknown
* `<<EXC:Description>>` — The requirement clearly indicates an error/exception behavior, but the exact exception type is unknown
* `<<MSG:Contains 'text'>>` — The requirement clearly indicates an error message or textual failure information, but the exact full message is unknown
* `<<VAL:Description>>` — A concrete value is required in the test case, but only its semantic meaning is known
* `<<OBJ:Description>>` — A structured object is involved, but only its semantic role is known and its internal fields cannot be safely inferred
* `<<FIELD:Description>>` — A field/value is known to matter semantically, but its exact representation or name cannot be safely derived
* `<<REL:Description>>` — A metamorphic/assertion relation when exact output cannot be directly computed but a requirement-supported relation can be stated

**Placeholder usage rules**:
- Prefer concrete values whenever they are directly derivable from the requirement, signature, or shared context.
- Use placeholders only for missing implementation-specific or structure-specific details.
- Do not use placeholders to hide uncertainty that should instead cause omission of that assertion.
- Do not introduce placeholders for behaviors not stated or implied by the requirement.
- If even the semantic role is unclear, do not invent a placeholder; omit that part of the test design.

**Step 1: Determine What Is Actually Observable**
For each method under test, identify only the observable behaviors that are justified by the provided information.

Allowed observable points:
* **Input domain**: Parameter categories and meaningful input partitions implied by the signature and requirement
* **Return behavior**: Return value existence, nullability, semantic result, or computable fields if supported by shared context
* **Error behavior**: Only if the requirement explicitly or strongly semantically implies failure/rejection/error handling
* **Message behavior**: Only if the requirement explicitly mentions an error message or textual feedback
* **State/interaction/side effect**: Only if explicitly described in the provided requirement/context

Do NOT infer the following unless explicitly supported:
* hidden fields inside returned objects
* internal helper method calls
* dependency invocation counts
* logging behavior
* state mutation
* exception types
* validation branches not described in the requirement

**Step 2: Extract Testable Semantics From the Requirement**
For each method, derive test scenarios from:
- the method signature
- the method semantic description
- any directly relevant shared context

Focus on:
* what the method is supposed to do
* which input categories are clearly meaningful
* which outputs are clearly observable
* which invalid/boundary cases are justified by the method name, parameter type, and requirement wording

Design rule:
- If a scenario is not supported by the requirement/signature/context, do not include it.
- If a scenario requires implementation knowledge to exist, skip it.
- If a scenario is valid but some concrete construction/output detail is unknown, keep the scenario and use placeholders only for the unknown part.

**Step 3: Test Design**
Design black-box logical test cases under these scenario categories, but only when justified by the provided information:

* **Positive**:
  - Normal business paths explicitly supported by the requirement
* **Boundary**:
  - Boundary inputs directly suggested by the parameter type or requirement semantics
  - Examples: empty string for `String`, zero for counts, minimal/maximal semantic cases when clearly meaningful
* **Negative**:
  - Only invalid/rejected inputs that are clearly implied by the requirement or common semantic constraints of the method signature
  - Do not assume all methods reject null/empty/invalid input unless the requirement or context supports it
* **Metamorphic**:
  - Only when exact output cannot be determined, but a valid relation between multiple inputs/outputs is supported by the requirement

  
**Assertion rules**:
- Assert only what can be justified from the current information.
- If shared_context fully specifies a result, compute the exact expected value and assert it directly.
- If a result is semantically clear but its concrete representation is unknown, use an appropriate placeholder.
- If the requirement indicates failure but not the exact failure mechanism, use `<<EXC:Description>>` only when exception behavior is actually implied.
- If the requirement indicates an error message, use `<<MSG:Contains 'text'>>` only for the message part, and only when the text is supported by the requirement.
- If neither exact value nor valid relation can be derived, do not invent an assertion.
- When designing assertions:

#### Case A — Applicable metamorphic relation exists

If:
- There is at least one valid and applicable metamorphic relation (MR) for the current test scenario

→ You MUST:
- Prefer the metamorphic relation as the primary assertion strategy
- Construct follow-up test inputs according to the MR transformation rules
- Execute both the source test input and the follow-up test input
- Assert the relational property between the two outputs
- For scenario aspects or properties not covered by the metamorphic relation, you may additionally use direct concrete assertions as supplementary checks.
- Keep the assertion consistent with the MR definition and its expected output relation

#### Case B — No applicable metamorphic relation exists

If:
- No MR is provided
- Or no available MR is applicable to the current test scenario

Then:
- If the algorithm is fully specified in shared_context, and the expected result can be manually computed

→ You MUST:
- Calculate the exact expected value
- Assert it directly using a concrete assertion

#### Case C — No applicable MR and expected output is not precisely derivable

If:
- No applicable MR exists
- And the algorithm is partially unknown
- Or the behavior depends on hidden logic
- Or the output is too complex to compute exactly
- Or there is ambiguity in the implementation

→ You MUST:
- Not fabricate any concrete expected value
- Not guess or invent expected outputs
- Skip that test case

**Step 4: Conservative Object and Value Construction**
When test inputs or expected outputs involve objects:
- If the object structure and fields are explicitly available in shared_context, use them concretely.
- If the object is required conceptually but instantiation details are unknown, use `<<NEW:ClassName(args)>>`.
- If even constructor arguments are unknown but the object role is known, use `<<OBJ:Description>>`.
- Never invent fields, constructors, nested properties, or enum values not present in the provided information.

Examples of correct conservative behavior:
- If input is a `String username`, you may use concrete string values such as `""`, `"alice"`, or boundary-length examples if justified.
- If output is `UserIdentity` and its fields are unknown, do not invent `id`, `name`, or `role`; use an object placeholder or only assert null/non-null/semantic relation if justified.
- If the requirement says "returns error message when username is invalid", you may use `<<MSG:Contains 'invalid username'>>` if that wording is supported, but not `<<EXC:InvalidUsernameException>>` unless throwing is implied.

**Step 5: Final Validation Before Output**
Before generating the final JSON:
- Remove any test case that depends on guessed implementation details.
- Remove any assertion that introduces unsupported fields, methods, classes, exceptions, or interactions.
- Ensure every placeholder is necessary and semantically justified.
- Ensure placeholders are not overused where concrete values are directly available.
- Ensure negative/error scenarios are included only when supported by requirement semantics.
- Ensure the final logical test cases remain black-box, requirement-driven, and implementation-agnostic.

**Output**: JSON only, strictly following the expected_output schema.