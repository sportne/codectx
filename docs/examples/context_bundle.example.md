# codectx context bundle

## Query
- budget: 4000
- file: <none>
- format: markdown
- goal: explain
- line: <none>
- symbol: PaymentService.authorize

## Anchor
- chunk_id: 7
- file: src/main/java/acme/PaymentService.java
- line: 12
- node_id: 7
- node_kind: callable
- node_name: authorize
- qualified_name: acme.PaymentService.authorize(PaymentRequest)
- symbol_key: java:src/main/java/acme/PaymentService.java#PaymentService.authorize(PaymentRequest)

## Index Health
- chunks: 11
- diagnostics: 0
- edges: 27
- feature.fts5: enabled
- files: 4
- index.cache_hits: 0
- index.cache_misses: 4
- index.cache_version: 1
- index.mode: full
- language.java: 4
- nodes: 11
- occurrences: 31
- unresolved_references: 11

## Context Items
### 1. target.definition

- file: src/main/java/acme/PaymentService.java:12-15
- reason: target definition
- score: 7.6768
- confidence: 1 (resolved/high)
- tokens: 29
- extractor: treesitter-java
- score_trace: confidence=0.5, edge_relevance=0.0, enclosing_context=0.0, exact_match=0.0, graph_proximity=0.0, lexical_match=1.0, redundancy=0.0, source_proximity=1.2, target=5.0, test_context=0.0, token_cost=-0.0232, total=7.6768

```java
public boolean authorize(PaymentRequest request) {
    validate(request);
    return gateway.charge(request);
  }
```

### 2. enclosing.type

- file: src/main/java/acme/PaymentService.java:5-23
- reason: enclosing type
- score: 2.4064
- confidence: 1 (resolved/high)
- tokens: 117
- extractor: treesitter-java
- score_trace: confidence=0.5, edge_relevance=0.0, enclosing_context=0.8, exact_match=0.0, graph_proximity=0.0, lexical_match=0.0, redundancy=0.0, source_proximity=1.2, target=0.0, test_context=0.0, token_cost=-0.0936, total=2.4064

```java
public class PaymentService {
  private final PaymentGateway gateway;

  public PaymentService(PaymentGateway gateway) {
    this.gateway = gateway;
  }

  public boolean authorize(PaymentRequest request) {
    validate(request);
    return gateway.charge(request);
  }

  private void validate(PaymentRequest request) {
    if (request == null) {
      throw new IllegalArgumentException("request");
    }
    Objects.requireNonNull(request.userId(), "userId");
  }
}
```

### 3. import

- file: src/main/java/acme/PaymentService.java:3
- reason: same-file import
- score: 1.8544
- confidence: 0.8 (strong heuristic)
- tokens: 7
- extractor: treesitter-java
- score_trace: confidence=0.4, edge_relevance=0.8, enclosing_context=0.0, exact_match=0.0, graph_proximity=0.0, lexical_match=0.0, redundancy=0.0, source_proximity=0.66, target=0.0, test_context=0.0, token_cost=-0.0056, total=1.8544

```java
import java.util.Objects;
```

### 4. neighborhood.type

- file: src/main/java/acme/PaymentRequest.java:3
- reason: referenced type
- score: 3.438
- confidence: 0.5 (weak heuristic)
- tokens: 15
- extractor: treesitter-java
- score_trace: confidence=0.25, edge_relevance=1.7, enclosing_context=0.0, exact_match=0.0, graph_proximity=1.5, lexical_match=0.0, redundancy=0.0, source_proximity=0.0, target=0.0, test_context=0.0, token_cost=-0.012, total=3.438

```java
public record PaymentRequest(String userId, int amount) {}
```

### 5. test.related

- file: src/test/java/acme/PaymentServiceTest.java:9-12
- reason: related test
- score: 1.1712
- confidence: 1 (resolved/high)
- tokens: 36
- extractor: treesitter-java
- score_trace: confidence=0.5, edge_relevance=0.0, enclosing_context=0.0, exact_match=0.0, graph_proximity=0.0, lexical_match=0.0, redundancy=0.0, source_proximity=0.0, target=0.0, test_context=0.7, token_cost=-0.0288, total=1.1712

```java
void authorize_fails_invalid_payment() {
    PaymentService service = new PaymentService(new PaymentGateway());
    service.authorize(null);
  }
```

### 6. test.related

- file: src/test/java/acme/PaymentServiceTest.java:4-7
- reason: related test
- score: 1.1664
- confidence: 1 (resolved/high)
- tokens: 42
- extractor: treesitter-java
- score_trace: confidence=0.5, edge_relevance=0.0, enclosing_context=0.0, exact_match=0.0, graph_proximity=0.0, lexical_match=0.0, redundancy=0.0, source_proximity=0.0, target=0.0, test_context=0.7, token_cost=-0.0336, total=1.1664

```java
void authorize_allows_valid_payment() {
    PaymentService service = new PaymentService(new PaymentGateway());
    service.authorize(new PaymentRequest("u1", 42));
  }
```

## Omitted
- src/main/java/acme/PaymentService.java:6: overlap score=1.332
- src/main/java/acme/PaymentService.java:17-22: overlap score=4.7358
- src/main/java/acme/PaymentService.java:8-10: overlap score=1.564

## Uncertainty
- unresolved relationship: Unresolved calls relationship from target: gateway.charge.

## Warnings
None.

## Trace
- file=src/main/java/acme/PaymentService.java, line=12, stage=anchor
- kind=target.definition, required=True, stage=candidate
- kind=enclosing.type, required=True, stage=candidate
- diagnostic_count=0, optional_count=7, relationship_count=2, stage=candidates, test_count=2
- optional_count=7, required_count=2, stage=rank
