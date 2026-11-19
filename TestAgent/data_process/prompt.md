# Role: Expert Reverse-Engineering Product Manager & Business Analyst

# Context & Objective
I am building a high-quality dataset for automated unit test generation research. I will provide you with the Ground Truth (GT) source code. 
Your task is to reverse-engineer a comprehensive, highly precise **SRS** based *strictly and exclusively* on the provided code.

# Strict Constraints (CRITICAL FOR DATASET INTEGRITY)
1. **Zero Hallucination:** You must NOT invent features, business rules, edge cases, or database states that do not explicitly exist in the code. If it is not implemented in the provided code, it is NOT a requirement.
2. **Mandatory Traceability:** Every single use case step, functional requirement, business rule, and exception MUST include a traceability tag pointing to the exact code location, formatted precisely as `[CodeRef: ClassName.methodName()]`.
3. **Test-Driven Focus:** Ensure all numeric thresholds, specific string messages, and boundary conditions found in the code are explicitly stated in the requirements, as these are critical for generating test assertions.

# Output Structure: The Reverse-Engineered SRS

## 1. Feature Overview & Purpose
Provide a concise summary (2-3 sentences) of the business capability implemented in this code. What problem does it solve?

## 2. Actors & Roles
Identify the entities that interact with this system. These could be human users (e.g., "Customer", "Admin") inferred from roles/permissions, or external systems/timers calling the public APIs.

## 3. Use Cases (Scenario Perspective)
Describe the end-to-end interactions from the Actor's perspective based on the public entry points (e.g., Controllers, Facades, or main Service methods). For each identified Use Case, provide:
- **Use Case ID & Name:** e.g., `UC-01: Process Online Payment`
- **Primary Actor:** Who initiates this?
- **Pre-conditions:** What state must be true before execution? (e.g., "Input order object must not be null"). 
- **Main Success Scenario (Happy Path):** The step-by-step flow of a successful execution. 
- **Alternate/Exception Flows:** What happens if validations fail or branches are taken? (e.g., "3a. If user balance is insufficient, reject transaction"). 

## 4. Functional Requirements (System Perspective)
Break down the Use Cases into granular, testable system capabilities. Use the "The system shall..." format. 
*Example:* 
- `FR-01`: The system shall calculate the total order price by summing the individual item prices. 
- `FR-02`: The system shall apply a 10% discount if the user is a VIP. 

## 5. Detailed Business Rules & Validations
Extract the core logic, mathematical formulas, and conditional constraints. This is the most critical section for boundary value analysis in unit testing.
- **Rule ID & Description:** (e.g., `BR-01: Age Validation`)
- **Condition/Formula:** Exactly specify the logic (e.g., "Age must be >= 18 and <= 99"). 
- **Action on Violation:** What happens if the rule is broken?

## 6. Data & State Requirements
Describe the data entities manipulated by this code based on parameters, DTOs, or domain objects.
- List required fields and their implied types/constraints (e.g., "email address (String, must contain '@')"). 
- Identify if the code implies reading from or writing to a persistent state (even if mocked via interfaces).

## 7. Exception & Error Handling
List all custom or standard exceptions explicitly thrown by the code.
- **Exception Type:** (e.g., `IllegalArgumentException`)
- **Trigger Condition:** The exact scenario that causes this exception. 
- **Error Message:** The exact string message associated with the error, if any.

# Input
Please analyze the following Ground Truth source code and generate the PRD:
<INSERT_GROUND_TRUTH_CODE_HERE>

-----
# Role: Expert Reverse-Engineering Software Architect

# Context & Objective
I am building a dataset for automated unit test generation research. I will provide you with the Ground Truth (GT) source code. 
Your task is to reverse-engineer an **Architecture Design Document (ADD)** based *strictly* on the provided code. 

# Strict Constraints (CRITICAL)
1. **Zero Hallucination:** Only describe the architecture that is actually implemented. Do not add idealized design patterns or theoretical layers if they are not explicitly present in the code.
2. **Focus on Testability:** Your output must clearly highlight module boundaries and dependencies, as this information is crucial for generating accurate Mocks/Stubs in unit testing.

# Output Structure

## 1. Logical Architecture & Layering
- Identify the structural layers present in the code (e.g., API Layer, Domain/Service Layer, Data Access/Repository Layer, Utility).
- Briefly describe the strict responsibility of each identified layer based on the code provided.

## 2. Modules and Provided Interfaces (APIs)
For each core module/component found in the code, document its public contract (Interfaces/Public Methods). For each interface, provide:
- **Component Name:** e.g., `PaymentProcessor`
- **Method Signature:** e.g., `boolean process(PaymentRequest req)`
- **Input Parameters & Types:** Description of what is required.
- **Return Type & Meaning:** What the component hands back to the caller.
- **Interface Description:** A brief summary of what this specific interface does architecturally.

## 3. External Dependencies & Integration Points
Identify all external boundaries that this code relies on. This is critical for test isolation.
- List all Interfaces or Classes that represent external systems (e.g., Database Repositories, Third-party HTTP clients, Message Queues).
- Specify which internal component calls them.

## 4. State & Data Management
Briefly describe how state is managed (e.g., stateless services passing DTOs, in-memory caching, direct database entity manipulation).

# Input
<INSERT_GROUND_TRUTH_CODE_HERE>

---------

# Role: Expert PlantUML Modeler & Systems Analyst

# Context & Objective
I am building a dataset for automated unit test generation research. I will provide you with the Ground Truth (GT) source code. 
Your task is to reverse-engineer highly accurate **Behavioral UML Sequence Diagrams** using PlantUML syntax, based *strictly* on the provided code.

# Strict Constraints (CRITICAL)
1. **100% Exact Call Chains:** The sequence diagram MUST perfectly mirror the method invocations in the code. Do not skip intermediate method calls.
2**No Hallucination:** Do not invent actors or external systems unless they are represented by an interface/class in the provided code.

# Output Requirements
1. Identify the 1 to 3 most complex or critical public entry methods (Use Cases) in the provided code.
2. For EACH identified entry method, generate a completely enclosed PlantUML sequence diagram block (`@startuml ... @enduml`).
3. Include parameter names and return values in the diagram arrows (e.g., `Service -> Repository : findById(userId)` -> `return UserEntity`).

# Output Format
Provide a brief heading for what the diagram represents, followed immediately by the raw PlantUML code block.

Example format:
### Sequence Diagram: Process Payment Use Case
```plantuml
@startuml
actor Client
participant OrderService
participant PaymentRepository

Client -> OrderService : process(orderId)
activate OrderService
... (details here including alt/opt) ...
return status
@enduml