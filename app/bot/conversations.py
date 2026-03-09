"""ConversationHandler flows — re-exported from handlers for modularity.

The actual conversation states and handlers are defined in handlers.py.
This module provides the ConversationHandler setup for the /add flow
and can be extended with additional conversation flows.
"""
# Conversation states are defined in handlers.py:
# NAME, URL, SELECTOR, THRESHOLDS, CONFIRM = range(5)
#
# The ConversationHandler is assembled in app/main.py init_bot()
