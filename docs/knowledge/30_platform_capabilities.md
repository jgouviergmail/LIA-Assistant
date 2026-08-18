# Platform capabilities

## Why can't I use a feature that the documentation describes?
Because not every LIA instance offers the same features, and that is
deliberate rather than a bug.

An administrator can switch eleven capabilities on or off for the whole instance,
from the settings panel, without redeploying and without editing a
configuration file:

dictation · speech synthesis · image generation · document generation · file
uploads · document spaces · web search · web browsing · skills · MCP servers ·
telephony

If one of them is off on your instance, LIA says so by name, in your language,
rather than failing without explanation.

## Will LIA still offer me something it cannot do?
No, and this is the part that matters day to day. When a capability is off, its
tools also disappear from the catalogue the planner is allowed to choose from.

That means LIA does not propose an action it would then be refused. You never
get the sequence where the assistant promises to do something and an error
appears a few seconds later — the promise is simply never made.

## Who decides, the administrator or the deployment?
Both, and the stricter one wins.

- The **deployment** (the environment the instance runs in) sets the outer
  bound: what is allowed at all.
- The **administrator** chooses inside that bound, from the settings panel.

The effective state is the logical AND. An administrator cannot re-enable
something the deployment forbids — and the panel says so explicitly: such a
capability carries an "Unavailable" badge and states the reason, instead of
offering a switch that would change nothing.

## Where do I see all this?
**Settings → Admin → System → Platform capabilities**, if you are an
administrator. Every row shows three things side by side: what the deployment
allows, what the administrator chose, and what is actually enforced.

## Does a capability being off affect my existing data?
No. Switching a capability off stops new use of it; it does not delete what
already exists. If document spaces are switched off, your documents stay where
they are and become reachable again when the capability is switched back on.

Connectors are a separate mechanism with its own admin section — disabling a
connector family does revoke active connections, which is why the two are not
managed in the same place.
