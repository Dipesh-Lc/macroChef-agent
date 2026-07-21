"""Phase 4 (expiry/waste tracking): `ConfirmedIngredient`'s new `purchase_date`
field and the `expires_soon`-derivation logic that reads it
(`app.schemas.inventory.ConfirmedIngredient._derive_expires_soon`,
`days_until_expiry`).

Covers:
- no `purchase_date` -> the caller's explicit `expires_soon` value passes
  through completely unchanged (backward compatibility for every existing
  caller/test that only ever set the bare boolean).
- `purchase_date` set -> `expires_soon` is DERIVED from it (age vs.
  `PERISHABLE_WINDOW_DAYS`), overriding whatever the caller also passed for
  `expires_soon`, at several ages (well within the window, exactly at the
  window, and past it).
- `days_until_expiry()` matches the same derivation, including going
  negative once already past the window.
"""

from datetime import date, timedelta

from app.schemas.inventory import PERISHABLE_WINDOW_DAYS, ConfirmedIngredient


def test_no_purchase_date_leaves_explicit_expires_soon_true_unchanged() -> None:
    item = ConfirmedIngredient(name="spinach", expires_soon=True)
    assert item.purchase_date is None
    assert item.expires_soon is True


def test_no_purchase_date_leaves_explicit_expires_soon_false_unchanged() -> None:
    item = ConfirmedIngredient(name="spinach", expires_soon=False)
    assert item.purchase_date is None
    assert item.expires_soon is False


def test_no_purchase_date_defaults_expires_soon_false() -> None:
    item = ConfirmedIngredient(name="spinach")
    assert item.expires_soon is False


def test_purchase_date_well_within_window_derives_not_expiring() -> None:
    item = ConfirmedIngredient(
        name="spinach", purchase_date=date.today() - timedelta(days=1)
    )
    assert item.expires_soon is False


def test_purchase_date_at_window_edge_derives_expiring() -> None:
    item = ConfirmedIngredient(
        name="spinach",
        purchase_date=date.today() - timedelta(days=PERISHABLE_WINDOW_DAYS),
    )
    assert item.expires_soon is True


def test_purchase_date_past_window_derives_expiring() -> None:
    item = ConfirmedIngredient(
        name="spinach",
        purchase_date=date.today() - timedelta(days=PERISHABLE_WINDOW_DAYS + 10),
    )
    assert item.expires_soon is True


def test_purchase_date_overrides_a_conflicting_explicit_expires_soon() -> None:
    # Caller passed expires_soon=False, but the purchase_date says otherwise
    # -- purchase_date is the source of truth once it's provided, per the
    # module docstring ("derived from it ... rather than requiring the
    # caller to set both redundantly").
    stale = ConfirmedIngredient(
        name="spinach",
        expires_soon=False,
        purchase_date=date.today() - timedelta(days=PERISHABLE_WINDOW_DAYS + 1),
    )
    assert stale.expires_soon is True

    fresh = ConfirmedIngredient(
        name="spinach",
        expires_soon=True,
        purchase_date=date.today(),
    )
    assert fresh.expires_soon is False


def test_days_until_expiry_none_without_purchase_date() -> None:
    assert ConfirmedIngredient(name="spinach").days_until_expiry() is None


def test_days_until_expiry_positive_within_window() -> None:
    item = ConfirmedIngredient(name="spinach", purchase_date=date.today())
    assert item.days_until_expiry() == PERISHABLE_WINDOW_DAYS


def test_days_until_expiry_negative_past_window() -> None:
    item = ConfirmedIngredient(
        name="spinach",
        purchase_date=date.today() - timedelta(days=PERISHABLE_WINDOW_DAYS + 3),
    )
    assert item.days_until_expiry() == -3
