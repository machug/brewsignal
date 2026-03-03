"""Context window management for the AI brewing assistant.

Handles token counting, context limit detection, and sliding-window
pruning to prevent hard failures on long conversations.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Safety margin: reserve tokens for output + overhead
OUTPUT_RESERVE_TOKENS = 10_000
# Target utilization after pruning (85% of budget)
PRUNE_TARGET_RATIO = 0.85


def count_context_tokens(
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
) -> int:
    """Count total tokens for messages + tools using litellm's tokenizer."""
    import litellm

    try:
        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        return litellm.token_counter(**kwargs)
    except Exception as e:
        logger.warning(f"Token counting failed, estimating: {e}")
        # Rough fallback: ~4 chars per token
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if tools:
            import json
            total_chars += len(json.dumps(tools))
        return total_chars // 4


def get_context_limit(model: str) -> int:
    """Get the max input token limit for a model."""
    from litellm import get_model_info

    try:
        info = get_model_info(model)
        return info.get("max_input_tokens", 200_000)
    except Exception:
        # Conservative default
        return 200_000


def get_token_budget(model: str) -> int:
    """Get the usable token budget (context limit minus output reserve)."""
    return get_context_limit(model) - OUTPUT_RESERVE_TOKENS


def prune_messages_if_needed(
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
) -> tuple[list[dict], int, bool]:
    """Prune messages if context exceeds budget.

    Sliding window strategy:
    - Always keep the system prompt (first message if role=system)
    - Always keep the most recent messages
    - Drop oldest message groups from the middle
    - A "group" is: assistant msg (possibly with tool_calls) + its tool results,
      or a standalone user/assistant message

    Returns: (pruned_messages, token_count, was_pruned)
    """
    budget = get_token_budget(model)
    token_count = count_context_tokens(model, messages, tools)

    if token_count <= budget:
        return messages, token_count, False

    target = int(budget * PRUNE_TARGET_RATIO)
    logger.info(
        f"Context pruning: {token_count} tokens exceeds budget {budget}, "
        f"targeting {target}"
    )

    # Separate system prompt from conversation
    system_msgs = []
    conversation = []
    for msg in messages:
        if msg.get("role") == "system" and not conversation:
            system_msgs.append(msg)
        else:
            conversation.append(msg)

    if len(conversation) <= 2:
        # Too few messages to prune meaningfully
        return messages, token_count, False

    # Group messages: each group is a coherent unit
    # (user msg, or assistant+tool_calls+tool_results, etc.)
    groups = _group_messages(conversation)

    # Binary search: keep removing oldest groups until under target
    # Always keep at least the last 2 groups (latest exchange)
    min_keep = 2
    keep_count = len(groups)

    while keep_count > min_keep:
        keep_count -= 1
        # Keep the last `keep_count` groups
        kept_groups = groups[-keep_count:]
        candidate = system_msgs + [msg for group in kept_groups for msg in group]
        candidate_tokens = count_context_tokens(model, candidate, tools)
        if candidate_tokens <= target:
            pruned_count = len(groups) - keep_count
            logger.info(
                f"Context pruned: dropped {pruned_count} message groups, "
                f"{token_count} -> {candidate_tokens} tokens"
            )
            return candidate, candidate_tokens, True

    # Even keeping minimum groups is too large - return what we can
    kept_groups = groups[-min_keep:]
    candidate = system_msgs + [msg for group in kept_groups for msg in group]
    candidate_tokens = count_context_tokens(model, candidate, tools)
    logger.warning(
        f"Context pruning: even minimum messages use {candidate_tokens} tokens "
        f"(budget: {budget})"
    )
    return candidate, candidate_tokens, True


def context_usage_info(
    model: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
) -> dict:
    """Get context usage information for frontend display."""
    token_count = count_context_tokens(model, messages, tools)
    budget = get_token_budget(model)
    limit = get_context_limit(model)

    return {
        "tokenCount": token_count,
        "tokenBudget": budget,
        "contextLimit": limit,
        "utilizationPercent": round((token_count / budget) * 100, 1) if budget > 0 else 0,
        "messageCount": len(messages),
    }


def _group_messages(messages: list[dict]) -> list[list[dict]]:
    """Group messages into coherent units for pruning.

    Groups:
    - A user message is its own group
    - An assistant message + any following tool messages form a group
    """
    groups: list[list[dict]] = []
    current_group: list[dict] = []

    for msg in messages:
        role = msg.get("role")

        if role == "user":
            # User messages start a new group
            if current_group:
                groups.append(current_group)
            current_group = [msg]
        elif role == "assistant":
            # Assistant starts a new group (may have tool calls following)
            if current_group:
                groups.append(current_group)
            current_group = [msg]
        elif role == "tool":
            # Tool results belong with the preceding assistant message
            current_group.append(msg)
        else:
            # Unknown role, treat as standalone
            if current_group:
                groups.append(current_group)
            current_group = [msg]

    if current_group:
        groups.append(current_group)

    return groups
