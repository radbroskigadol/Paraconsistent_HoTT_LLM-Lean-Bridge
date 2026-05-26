import Lake
open Lake DSL

package shadowproof where

require mathlib from git
  "https://github.com/leanprover-community/mathlib4" @ "809c3fb3b5c8f5d7dace56e200b426187516535a"

@[default_target]
lean_lib ShadowProof where
