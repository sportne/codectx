# Code Context Bundle

Goal: `explain`
Budget: ~8,000 tokens
Repository: `example-repo`
Anchor: `PaymentService.authorize`

## Index health

- Indexed files: 142
- Java files: 76
- C++ files: 0
- Parser diagnostics: 2
- Unresolved call-like references: 317
- Extraction mode: Tree-sitter heuristic

## Target

- Symbol: `PaymentService.authorize`
- Kind: `callable`
- File: `src/main/java/acme/PaymentService.java`
- Lines: 42-118

## Ranked context

### 1. Target definition

Reason: primary target definition
Confidence: 0.95
Extractor: `tree-sitter-java`
File: `src/main/java/acme/PaymentService.java`
Lines: 42-118

```java
// source snippet goes here
```

### 2. Enclosing type

Reason: enclosing class contains fields used by target
Confidence: 0.90
Extractor: `tree-sitter-java`
File: `src/main/java/acme/PaymentService.java`
Lines: 12-140

```java
// source snippet goes here
```

## Uncertainty notes

- `gateway.charge(...)` appears to be called by the target, but receiver type was not resolved. Confidence: 0.42.
- Parser diagnostics exist in unrelated files; see index health for details.

## Omitted candidates

- `AuditLogger.log`: omitted due to low score under token budget.
