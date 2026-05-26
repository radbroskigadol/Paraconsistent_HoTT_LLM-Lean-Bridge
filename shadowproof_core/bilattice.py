from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class BilatticeValue:
    """
    The four-element ShadowHoTT bilattice L = 2 × 2.

    Coordinates are (truth, refutation).  Designation is the binary predicate
    `truth == True`; it is not a probability or score.  The De Morgan
    involution swaps the coordinates.  Path composition is interpreted by the
    bilattice meet: truth is fragile (AND), refutation accumulates (OR).
    """

    truth: bool
    refutation: bool

    @classmethod
    def top(cls) -> "BilatticeValue":
        """⊤_L = (⊤, ⊥): classical proof / positive evidence only."""
        return cls(True, False)

    @classmethod
    def bottom(cls) -> "BilatticeValue":
        """⊥_L = (⊥, ⊤): classical refutation / negative evidence only."""
        return cls(False, True)

    @classmethod
    def both(cls) -> "BilatticeValue":
        """⊥⊤_L = (⊤, ⊤): designated glut / simultaneous proof and refutation."""
        return cls(True, True)

    @classmethod
    def neither(cls) -> "BilatticeValue":
        """n_L = (⊥, ⊥): gap / no positive or negative classical evidence."""
        return cls(False, False)

    @staticmethod
    def _require_bool(label: dict[str, Any], key: str) -> bool:
        if key not in label:
            raise ValueError(f"bilattice coordinate dict missing {key!r}")
        value = label[key]
        if not isinstance(value, bool):
            raise ValueError(f"bilattice coordinate {key!r} must be a real JSON boolean, not {type(value).__name__}")
        return value

    @classmethod
    def from_label(cls, label: str | "BilatticeValue" | dict[str, Any]) -> "BilatticeValue":
        if isinstance(label, BilatticeValue):
            return label
        if isinstance(label, dict):
            if "truth_coordinate" in label or "refutation_coordinate" in label:
                return cls(cls._require_bool(label, "truth_coordinate"), cls._require_bool(label, "refutation_coordinate"))
            if "truth" in label or "refutation" in label:
                return cls(cls._require_bool(label, "truth"), cls._require_bool(label, "refutation"))
            label = str(label.get("label", "gap"))
        s = str(label).strip().lower()
        aliases = {
            "top": cls.top(),
            "⊤_l": cls.top(),
            "proof": cls.top(),
            "accepted": cls.top(),
            "bottom": cls.bottom(),
            "⊥_l": cls.bottom(),
            "refuted": cls.bottom(),
            "reject": cls.bottom(),
            "both": cls.both(),
            "glut": cls.both(),
            "glutty": cls.both(),
            "⊥⊤_l": cls.both(),
            "inconsistent_designated": cls.both(),
            "neither": cls.neither(),
            "gap": cls.neither(),
            "n_l": cls.neither(),
            "unknown": cls.neither(),
            "unchecked": cls.neither(),
        }
        if s not in aliases:
            raise ValueError(f"unknown bilattice label: {label!r}")
        return aliases[s]

    @property
    def designated(self) -> bool:
        return self.truth

    @property
    def classical(self) -> bool:
        return self in {TOP_L, BOTTOM_L}

    @property
    def nonreal(self) -> bool:
        """The non-classical labels used by No-Glutty-J conservation checks."""
        return self in {BOTH_L, NEITHER_L}

    @property
    def label(self) -> str:
        if self == TOP_L:
            return "top"
        if self == BOTTOM_L:
            return "bottom"
        if self == BOTH_L:
            return "both"
        return "neither"

    @property
    def pretty(self) -> str:
        if self == TOP_L:
            return "⊤_L"
        if self == BOTTOM_L:
            return "⊥_L"
        if self == BOTH_L:
            return "⊥⊤_L"
        return "n_L"

    def involution(self) -> "BilatticeValue":
        """De Morgan involution ∼(a,b) = (b,a)."""
        return BilatticeValue(self.refutation, self.truth)

    def meet(self, other: "BilatticeValue") -> "BilatticeValue":
        """Truth-order meet ∧_L for path composition: (t₁∧t₂, r₁∨r₂)."""
        other = BilatticeValue.from_label(other)
        return BilatticeValue(self.truth and other.truth, self.refutation or other.refutation)

    def join(self, other: "BilatticeValue") -> "BilatticeValue":
        """Truth-order join ∨_L dual to meet: (t₁∨t₂, r₁∧r₂)."""
        other = BilatticeValue.from_label(other)
        return BilatticeValue(self.truth or other.truth, self.refutation and other.refutation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "pretty": self.pretty,
            "truth_coordinate": self.truth,
            "refutation_coordinate": self.refutation,
            "designated": self.designated,
            "classical": self.classical,
            "nonreal": self.nonreal,
        }

    def __str__(self) -> str:
        return self.label


def bilattice_meet_all(values: Iterable[BilatticeValue], default: BilatticeValue | None = None) -> BilatticeValue:
    it = iter(values)
    try:
        acc = next(it)
    except StopIteration:
        return default if default is not None else NEITHER_L
    acc = BilatticeValue.from_label(acc)
    for value in it:
        acc = acc.meet(BilatticeValue.from_label(value))
    return acc


def aut_L() -> dict[str, dict[str, str]]:
    """
    The exposed order-two symmetry generated by identity and the De Morgan
    involution.  Composition table is Z/2Z.
    """
    return {
        "identity": {v.label: v.label for v in L_VALUES},
        "involution": {v.label: v.involution().label for v in L_VALUES},
        "composition_table": {
            "identity∘identity": "identity",
            "identity∘involution": "involution",
            "involution∘identity": "involution",
            "involution∘involution": "identity",
        },
    }


def coordinate_tuple(value: BilatticeValue | str | dict[str, Any]) -> tuple[bool, bool]:
    """Return the raw (truth, refutation) coordinates of a bilattice value."""
    v = BilatticeValue.from_label(value)
    return (v.truth, v.refutation)


def demorgan_order_two_report() -> dict[str, Any]:
    """Executable coordinate-level witness for the De Morgan Z/2 symmetry.

    This mirrors the standalone Lean formalization in
    lean_project_template/ShadowProof/DemorganSymmetry.lean.  It deliberately
    reports designation preservation separately: the coordinate swap is the
    nontrivial De Morgan order-two symmetry, but it is not designation-preserving
    because it sends ⊤_L to ⊥_L.
    """
    table = {v.label: v.involution().label for v in L_VALUES}
    return {
        "carrier": "L = Bool × Bool",
        "operation": "demorgan_swap(truth, refutation) = (refutation, truth)",
        "order_two": all(v.involution().involution() == v for v in L_VALUES),
        "fixed_points": [v.label for v in L_VALUES if v.involution() == v],
        "swapped_pair": ["top", "bottom"],
        "composition_table": aut_L()["composition_table"],
        "action_table": table,
        "meet_associative": all(a.meet(b).meet(c) == a.meet(b.meet(c)) for a in L_VALUES for b in L_VALUES for c in L_VALUES),
        "join_associative": all(a.join(b).join(c) == a.join(b.join(c)) for a in L_VALUES for b in L_VALUES for c in L_VALUES),
        "absorption": all(a.meet(a.join(b)) == a and a.join(a.meet(b)) == a for a in L_VALUES for b in L_VALUES),
        "demorgan_meet_join_duality": all(a.meet(b).involution() == a.involution().join(b.involution()) for a in L_VALUES for b in L_VALUES),
        "demorgan_join_meet_duality": all(a.join(b).involution() == a.involution().meet(b.involution()) for a in L_VALUES for b in L_VALUES),
        "designation_preserving": False,
        "designation_note": "The nontrivial De Morgan swap sends top to bottom, so designation preservation leaves only identity.",
    }


TOP_L = BilatticeValue(True, False)
BOTTOM_L = BilatticeValue(False, True)
BOTH_L = BilatticeValue(True, True)
NEITHER_L = BilatticeValue(False, False)
L_VALUES = (TOP_L, BOTTOM_L, BOTH_L, NEITHER_L)
