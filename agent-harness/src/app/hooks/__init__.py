"""Hook registry.

Import your hooks here and add instances to the HOOKS list.
Hooks run before/after every tool call for safety enforcement.

HOW TO ADD A HOOK:
    1. Create a new file in hooks/, e.g. hooks/my_hook.py
    2. Subclass Hook and override before_tool_call / after_tool_call:

        from agent_harness import Hook, HookResult

        class MyHook(Hook):
            def before_tool_call(self, tool_name, args):
                if dangerous_condition(args):
                    return HookResult(allowed=False, reason="Explain why blocked")
                return HookResult(allowed=True)

            def after_tool_call(self, tool_name, args, result):
                return sanitize(result)

    3. Import it here and add an instance to the HOOKS list.
"""

from app.hooks.content_filter import SafetyScopeGuardHook
from app.hooks.phi_redaction import PHIRedactionHook

HOOKS = [
    PHIRedactionHook(),
    SafetyScopeGuardHook(),
]
