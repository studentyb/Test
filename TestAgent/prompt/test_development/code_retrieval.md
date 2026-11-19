
You are a Code Analysis Expert. Analyze the test case input and identify all project-defined Types/Classes or Methods that must be retrieved from the **{{language.capitalize()}}** codebase in order to convert the logical test cases into executable test code.

Your task is retrieval planning, not implementation.
Return only the project-defined code elements whose definitions are necessary for test-code generation.

### Extraction Goal

Identify only the **project-defined** classes or methods whose definitions are needed to:
- locate and invoke the focal method,
- construct required project objects,
- understand mocked collaborators,
- resolve project-defined parameter types or return types,
- verify assertions that depend on project-defined classes/methods/fields.

Do **not** retrieve anything from:
{% if language == "java" %}
- JDK / Java standard library,
- third-party libraries,
- frameworks,
- test libraries,
- servlet/web/framework infrastructure.
{% elif language == "python" %}
- Python standard library,
- third-party libraries,
- frameworks,
- test libraries (pytest, unittest),
- web frameworks infrastructure.
{% endif %}

### Extraction Rules

**The focal point is mandatory retrieval context.**

1. **Focal Point First**
   - The focal method/function is mandatory retrieval context and must always be retrievable.
   - If the owning class of the `focal_method` is explicitly known from the test-case input, retrieve that class.
   - If the owning class is NOT explicitly known, retrieve the focal method/function name itself as a method-level query so the real implementation can be located first.
   - Once the owning class is known, class retrieval is preferred over retrieving additional methods/functions from that class.
   - Never omit the focal method/function from retrieval planning.

2. **Project-Defined Types in Signatures**
   - Extract project-defined classes/types appearing in:
     - focal method parameters,
     - focal method return type,
     - relevant generic type arguments if they are project-defined.
   - Example:
     - `List<User>` (Java) or `List[User]` (Python) → retrieve `User`, not `List`.

3. **Object Construction Requirements**
   - If test inputs, mocks, or assertions contain placeholders such as:
     - `<<NEW:ClassName(args)>>`
     - `<<OBJ:Description>>`
   - retrieve the relevant project-defined class if its definition is needed for object construction or structure understanding.
   - For `<<NEW:ClassName(args)>>`, retrieve `ClassName` as a class.

4. **Mocks and Collaborators**
   - From the `mocks` section, extract only project-defined collaborators.
   - If a mock refers to a dependency method on a project-defined class or interface, retrieve the class/interface, not the method.
   - If the collaborator is clearly a framework or third-party type, exclude it.

5. **Assertions and Observables**
   - From `asserts` and `observables`, retrieve only project-defined code elements whose definitions are needed to understand:
     - project-defined return objects,
     - project-defined fields/getters/properties involved in assertions,
     - project-defined collaborators whose interaction is asserted.
   - Do not retrieve local variables, temporary names, or ordinary {% if language == "java" %}Java{% elif language == "python" %}Python{% endif %} library members.

6. **Class-First Principle**
   - If a class is retrieved, do NOT separately retrieve any method/function defined inside that class.
   - The class definition already provides its methods/functions, fields, constructors, and related structure.

7. **Only Retrieve What Is Necessary**
   - Do not over-retrieve.
   - Include only code elements whose definitions are necessary for converting the logical test into executable {{language.capitalize()}} test code.
   - Ignore names that are mentioned but not needed for code generation.

### Deduplication Rules (CRITICAL)

8. **No duplicates**
   - Each query name must appear at most once.

9. **Normalize to short names only**
   - Use only the short class or method/function name.
   - No package path, no fully qualified name, no signature.

### Exclusion Rules (CRITICAL)

10. **Do NOT retrieve built-in, standard library, framework, or third-party elements**
    Exclude examples such as:
{% if language == "java" %}
    - Java built-in / common JDK types: `String`, `Integer`, `Long`, `Boolean`, `Object`, `Class`
    - Collections and generics containers: `List`, `Map`, `Set`, `Collection`, `ArrayList`, `HashMap`, `LinkedList`
    - Exceptions: `Exception`, `RuntimeException`, `IllegalArgumentException`, `NullPointerException`, `IOException`, etc.
    - JDK utility types: `Optional`, `Stream`, `Comparable`, `Serializable`, `Iterable`, `LocalDate`, `BigDecimal`
    - Framework/test/library types: `ResponseEntity`, `HttpServletRequest`, `HttpServletResponse`, `Mockito`, `Mock`, `InjectMocks`, `Autowired`, etc.
    - Any clearly external dependency not defined in the project codebase
{% elif language == "python" %}
    - Python built-in types: `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `set`, `None`, `type`, `object`
    - Collections: `list`, `dict`, `set`, `tuple`, `collections.deque`, `collections.Counter`
    - Standard library types: `datetime`, `pathlib.Path`, `typing.Optional`, `typing.Union`, `typing.List`, `typing.Dict`, `typing.Any`
    - Exceptions: `Exception`, `ValueError`, `TypeError`, `KeyError`, `IndexError`, `IOError`, `OSError`, etc.
    - Framework/test/library types: `pytest`, `unittest`, `unittest.mock`, `Mock`, `patch`, `MagicMock`
    - Web framework types: `flask.Request`, `flask.Response`, `django.http.HttpRequest`, etc.
    - Any clearly external dependency not defined in the project codebase
{% endif %}

11. **Do NOT retrieve the following**
    - variable names such as `result`, `user`, `response`
    - literal values
    - assertion expressions/operators
    - placeholder tags themselves such as `<<NULL>>`, `<<VAL:...>>`, `<<REL:...>>`
    - methods/functions if their owning class is already being retrieved

12. **Field/Getter/Property Handling**
    - If an assertion references something like `result.getStatus()` (Java) or `result.status` (Python), do not retrieve `getStatus` or `status` separately when the return type is a project-defined class.
    - Retrieve the project-defined class instead.
    - If the return type cannot be safely identified as a project-defined class, do not guess.

13. **Method/Function Retrieval**
    - Use `search_type: "method"` (Java) or `search_type: "function"` (Python) only when a project-defined method/function truly needs separate retrieval and is not already covered by retrieving its owning class.
    - In most cases, prefer retrieving the owning class.

14. **Ambiguity Handling**
    - If a symbol may be project-defined or external, include it only when the test-case input strongly suggests it belongs to the project.
    - When in doubt, prefer omission over guessing.

### Input for Analysis:

{{test_case_input}}

uml_class:

{{uml_class}}

### Output Format:
Strict JSON array only. No preamble, no explanation.
- `query`: Short name of the type or method/function.
- `search_type`: `"class"` or `"method"` (Java) / `"function"` (Python).

```json
[
  { "query": "OrderProcessor", "search_type": "class" },
  { "query": "processPayment", "search_type": "{% if language == 'java' %}method{% elif language == 'python' %}function{% endif %}" }
]
```
