import json
import numpy
import openai
import elevenlabs
import memory
import helpers

openai_path = "Data/openai_key.txt"
eleven_path = "Data/eleven_key.txt"
prompt_path = "Data/gpt_prompt.txt"
admins_path = "Data/admins.txt"
markov_path = "Data/markov_chain.json"

voice_memory = dict()

with open(markov_path, 'r', encoding='utf8') as markov:
    markov_chain = json.load(markov)

def get_ai_response(messages: list) -> str:
    global previous_usage

    chat = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
    response = chat.choices[0].message.content
    previous_usage = chat.usage

    # Remove quotation marks from the message if GPT decided to use them
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]

    return response

async def chat_command(context, update=None):
    # Load and set the OpenAI API key
    with open(openai_path) as f:
        openai.api_key = f.readline().strip()

    # Load the system prompt
    with open(prompt_path) as f:
        system_prompt = ''.join(f.readlines())

    loaded_memory = memory.load_memory()

    user_message = await helpers.get_args_list(context, update)

    # Create a prompt for GPT that includes the user's name and message, as well as whether it was a private message or not
    user_prompt = await memory.generate_user_prompt(' '.join(user_message), context, update)

    # Place the system prompt before the loaded memory to instruct the AI how to act
    messages = [{"role": "system", "content": system_prompt}] + loaded_memory
    messages.append({"role": "user", "content": user_prompt})

    # Have GPT generate a response to the user prompt
    try:
        response = get_ai_response(messages)
    except openai.error.ServiceUnavailableError:
        return "*beep-boop* CONNECTION TIMED OUT *beep-boop*"

    # Add the user's prompt and the AI's response to memory
    memory.append_to_memory(user_prompt, response, loaded_memory)

    return response

# Markov-powered Text Generation Command
def generate_markov_text(min_length=2, max_length=255) -> str:
    null_token = "NULL_TOKEN"

    chosen_tokens = []
    while True:
        if not chosen_tokens:
            prev_token = null_token
        else:
            prev_token = chosen_tokens[-1]

        new_token = numpy.random.choice(list(markov_chain[prev_token].keys()), 1, p=list(markov_chain[prev_token].values()))[0]

        if new_token == null_token:
            if len(chosen_tokens) < min_length:
                chosen_tokens = []
                continue
            break

        chosen_tokens.append(new_token)
        if len(chosen_tokens) >= max_length:
            break

    output_message = ' '.join(chosen_tokens)
    output_message = output_message[0].upper() + output_message[1:]
    return output_message

async def wisdom_command(context, update=None):
    message_text = generate_markov_text()

    user_prompt = await memory.generate_user_prompt("O, wise and powerful girthbot, please grant me your wisdom!", context, update)
    memory.append_to_memory(user_prompt, message_text)

    return message_text

# Elevenlabs-powered
async def say_command(context, update=None):
    user_message = await helpers.get_args_list(context, update)
    if not user_message:
        try:
            text_prompt = memory.load_memory()[-1]['content']
        except IndexError:
            return "My memory unit appears to be malfuncitoning."

    else:
        text_prompt = ' '.join(user_message)

    soft_cap = 800
    hard_cap = 1000
    for index, char in enumerate(text_prompt):
        if index >= soft_cap and char in ['.', '?', '!']:
            text_prompt = text_prompt[:index]
            break
        elif index >= hard_cap:
            text_prompt = text_prompt[:index]

    if text_prompt in voice_memory:
        audio = voice_memory[text_prompt]

    else:
        with open(eleven_path) as f:
            elevenlabs.set_api_key(f.readline().strip())

        try:
            audio = elevenlabs.generate(
                text=text_prompt,
                voice="Girthbot",
                model='eleven_monolingual_v1'
            )

        except elevenlabs.api.error.APIError:
            return "Sorry, but Stephen is a cheap bastard and didn't renew his elevenlabs subscription."

        voice_memory[text_prompt] = audio

    await context.bot.send_voice(chat_id=update.effective_chat.id, voice=audio)

# Misc chat commands
async def pressf_command(context, update=None):
    user_prompt = await memory.generate_user_prompt("F's in the chat boys.", context, update)
    memory.append_to_memory(user_prompt, "F")

    return "F"

async def help_command(context, update=None):
    help_string = """\
Look upon my works, ye mighty, and despair:
/sound (play a sound effect)
/soundlist (see what sounds are available)
/search (look for sounds)
/random (play a random sound effect)
/newsounds (see what new sounds are available)
/roll (roll a dice)
/pressf (pay respects)
/wisdom (request my wisdom)
/chat (talk to me)"""

    user_prompt = await memory.generate_user_prompt("What chat commands are available?.", context, update)
    memory.append_to_memory(user_prompt, help_string)

    return help_string
