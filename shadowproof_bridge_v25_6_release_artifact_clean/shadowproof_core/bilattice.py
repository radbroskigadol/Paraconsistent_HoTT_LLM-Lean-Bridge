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

    @classmethod
    def from_label(cls, label: str | "BilatticeValue" | dict[str, Any]) -> "BilatticeValue":
        if isinstance(label, BilatticeValue):
            return label
        if isinstance(label, dict):
            if "truth_coordinate" in label or "refutation_coordinate" in label:
                return cls(_strict_coordinate(label.get("truth_coordinate"), "truth_coordinate"), _strict_coordinate(label.get("refutation_coordinate"), "refutation_coordinate"))
            if "truth" in label and "refutation" in label:
                return cls(_strict_coordinate(label.get("truth"), "truth"), _strict_coordinate(label.get("refutation"), "refutation"))
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
        """Truth-order meet ∧_L used for path composition.

        In coordinates, (t, f) ∧_L (t′, f′) = (t ∧ t′, f ∨ f′):
        truth evidence is fragile under composition, while refutation evidence
        accumulates.  Thus ⊤_L is the meet identity and ⊥_L is absorbing.
        """
        other = BilatticeValue.from_label(other)
        return BilatticeValue(self.truth and other.truth, self.refutation or other.refutation)

    def join(self, other: "BilatticeValue") -> "BilatticeValue":
        """Truth-order join ∨_L dual to ``meet``.

        (t, f) ∨_L (t′, f′) = (t ∨ t′, f ∧ f′).  The De Morgan
        involution satisfies ∼(a ∧ b) = ∼a ∨ ∼b and
        ∼(a ∨ b) = ∼a ∧ ∼b.
        """
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
        "designation_preserving": False,
        "designation_note": "The nontrivial De Morgan swap sends top to bottom, so designation preservation leaves only identity.",
    }


TOP_L = BilatticeValue(True, False)
BOTTOM_L = BilatticeValue(False, True)
BOTH_L = BilatticeValue(True, True)
NEITHER_L = BilatticeValue(False, False)
L_VALUES = (TOP_L, BOTTOM_L, BOTH_L, NEITHER_L)


def _strict_coordinate(value: Any, field: str) -> bool:
    """Parse a bilattice coordinate without Python truthiness coercion.

    ``bool("false")`` is ``True`` in Python, which would silently turn a
    serialized refutation/truth coordinate into the wrong mathematical point.
    Runtime schemas require JSON booleans; this function enforces the same rule
    for internal/dict callers.
    """
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean, not {type(value).__name__}")
