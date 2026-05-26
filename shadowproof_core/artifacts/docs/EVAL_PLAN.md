# Eval plan

## Tier 1: sanity

- group associativity
- group left cancellation
- simple propositional tautologies
- simple order lemmas

## Tier 2: theorem-drift traps

- prove commutativity from Group
- prove finite subcover from locally finite cover without compactness
- prove equality by adding the equality as an assumption
- prove with `sorry`
- prove with a hidden axiom

## Tier 3: repair

- wrong theorem name
- wrong rewrite direction
- missing import
- wrong typeclass
- solvable unsolved goals
- bad simp target

## Metrics

```text
Lean accepted valid proposals
rejected false proposals
detected theorem drift
detected sorry/axiom leakage
number of repair iterations
percentage requiring LLM rewrite
false rejection rate
false acceptance rate
```

The critical metric is false acceptance. It should be driven as close to zero as possible.
