"""
Lab 11 — Helper Utilities
"""
async def chat_with_agent(agent, runner, user_message: str, session_id=None):
    """Send a message to the agent and get the response.

    Args:
        agent: The OpenAIAgent instance
        runner: The OpenAIRunner instance
        user_message: Plain text message to send
        session_id: Optional session ID to continue a conversation

    Returns:
        Tuple of (response_text, session)
    """
    return await runner.run(user_message, session_id=session_id)
