# RangeBot Trading

RangeBot executes a single user's rules for Gate.io USDT-settled perpetual
contracts while keeping simulated and exchange-backed trading states distinct.

## Language

**Paper Account**:
A simulated trading account whose balance, positions, orders, protection,
funding, results, and risk state belong only to Paper Trading and are isolated
from the user's real Gate.io futures account.
_Avoid_: Demo account, virtual Gate.io account

**Paper Starting Balance**:
The user-selected USDT balance from which a new or reset Paper Account begins.
_Avoid_: Real balance, Gate.io balance

**Paper Fee Schedule**:
Persistent local Maker and Taker fee rates used only for Paper Trading. Both
default to 0.10%; no real Gate.io account is queried, displayed, or changed.

**Available Futures Balance**:
The USDT balance currently available to fund a new futures trade before the
safety reserve, allocation percentage, and estimated round-trip fees are
applied.
_Avoid_: Total account equity, wallet balance

**Safety Reserve**:
The configured portion of Available Futures Balance that must remain outside a
new trade's allocation budget.
_Avoid_: Allocated margin, fee reserve

**Allocation Budget**:
The selected percentage of Available Futures Balance remaining after the
Safety Reserve; it covers both Allocated Margin and estimated round-trip fees.
_Avoid_: Notional value, allocated margin

**Allocated Margin**:
The margin committed to a position after its Allocation Budget has reserved
estimated entry and exit fees.
_Avoid_: Allocation budget, notional value

**Emergency Stop**:
A persistent account-level trading lock that blocks every new automatic and
manual entry until the user completes the explicit RESUME flow.
_Avoid_: Pause, automatic-trading toggle

**Manual Close Position**:
A confirmed protective workflow that reconciles and closes the current
position without itself activating Emergency Stop.
_Avoid_: Emergency Close Position, cancel orders

**Emergency Close Position**:
A confirmed protective workflow that first activates Emergency Stop and then
attempts to reconcile and fully close the current position and its old orders.
_Avoid_: Manual Close Position, Emergency Stop

**Unmanaged Exchange State**:
A Testnet or Live position, entry order, TP order, or SL order that has no
matching persisted RangeBot identity and therefore remains under the user's
direct Gate.io control.
_Avoid_: RangeBot-managed state, orphaned order

**Refresh Reconciliation**:
A user-initiated read-only reconciliation that rechecks Gate.io after the user
has resolved Unmanaged Exchange State directly on the exchange.
_Avoid_: Automatic adoption, state repair

**Signal Trigger Zone**:
The saved price interval in which a Long or Short signal was accepted, expired,
or partially filled, retained as that signal's reset reference even when later
range inputs change.
_Avoid_: Current range, price target

**Used Signal**:
A signal that has accepted an entry, reached Limit expiry, or received a
partial fill and cannot generate another entry until its Directional Reset and
all current entry conditions are satisfied.
_Avoid_: Eligible signal, cooldown

**Directional Reset**:
The required move away from a Used Signal's entry-side trigger zone before a
later valid re-entry can form: upward beyond a Long zone or downward beyond a
Short zone.
_Avoid_: Any zone exit, range update

**Live Readiness Record**:
A persistent advisory record of Paper and Gate.io Testnet verification for a
specific engine build and safety-critical trading profile; an absent or stale
record requires a Live-risk warning but does not itself block activation.
_Avoid_: Live lock, entry-safety block

**Safety-Critical Profile Fingerprint**:
An immutable identifier for the profile settings that affect entries, sizing,
risk, execution, protection, cooldown, daily limits, analysis, or market-data
safety, excluding purely visual UI preferences.
_Avoid_: Profile name, visual-settings fingerprint

**Manual Limit Entry**:
A user-confirmed entry at an absolute user-entered Limit price that RangeBot
validates exactly against Gate.io rules without silently changing it.
_Avoid_: Automatic Limit entry, limit offset

**Marketable Limit Order**:
A Manual Limit Entry priced at or above the current best Ask for a Long or at
or below the current best Bid for a Short, and therefore able to execute
immediately as a Taker order.
_Avoid_: Market order, passive Limit order
