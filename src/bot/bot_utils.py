"""
Bot utilities for handling both sync and async python-telegram-bot versions
"""
import asyncio
from src.utils.logger import print_status

def safe_bot_call(bot_method, *args, **kwargs):
    """
    Safe wrapper for bot method calls that handles both sync and async versions
    """
    try:
        result = bot_method(*args, **kwargs)
        # If it's a coroutine (async), we need to run it
        if asyncio.iscoroutine(result):
            try:
                # Try to get or create event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, create a task and wait for it
                    task = asyncio.create_task(result)
                    # For sync context, we need to run this differently
                    return asyncio.run_coroutine_threadsafe(result, loop).result(timeout=30)
                else:
                    # If loop is not running, run until complete
                    return loop.run_until_complete(result)
            except RuntimeError:
                # No event loop, create one
                return asyncio.run(result)
        else:
            # Synchronous result, return as-is
            return result
    except Exception as e:
        print_status(f"Error in bot call: {e}", "ERROR")
        return None

# Alternative simpler approach - try to handle the coroutine warnings
def handle_bot_call(bot_method, *args, **kwargs):
    """
    Simple wrapper that just executes the bot method and ignores coroutine warnings
    """
    try:
        result = bot_method(*args, **kwargs)
        # Check if it's a coroutine and try to handle it
        if hasattr(result, '__await__'):
            # It's async, try to run it
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                final_result = loop.run_until_complete(result)
                loop.close()
                return final_result
            except Exception as async_err:
                print_status(f"Async execution error: {async_err}", "DEBUG")
                return result  # Return the coroutine itself if we can't execute it
        return result
    except Exception as e:
        print_status(f"Bot call error: {e}", "ERROR")
        return None
