import random
import re

# Stat Roll command
def statroll_command(update, context):
    valid_games = ["dnd", "coc", "mythras"]
    try:
        game = context.args[0].lower()
        if game not in valid_games:
            raise IndexError
        
    except IndexError:
        reply_name = update.message.from_user.username
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"@{reply_name} please supply a game name. Options are {', '.join(valid_games)}")
        return

    roll_string = "this should not appear"
    if game == "dnd":
        roll_string = get_dnd_roll()
        
    if game == "coc":
        roll_string = get_coc_roll()
        
    if game == "mythras":
        roll_string = get_mythras_roll()
        
    context.bot.send_message(chat_id=update.effective_chat.id, text=roll_string)

def get_coc_roll() -> str:
    roll_string = ""
    for stat in ["STR", "CON", "DEX", "APP", "POW"]:
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        d3 = random.randint(1, 6)

        roll_string = "\n".join([roll_string, f"{stat}: {5*(d1 + d2 + d3)}"])

    for stat in ["SIZ", "INT", "EDU", "LUC"]:
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)

        roll_string = "\n".join([roll_string, f"{stat}: {5*(d1 + d2 + 6)}"])

    roll_string = "\n".join([roll_string, f"Bonus: {random.randint(1, 10)}"])
    return roll_string
    
def get_dnd_roll() -> str:
    roll_string = ""
    for stat in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        four_rolls = [random.randint(1, 6) for _ in range(4)]
        del four_rolls[four_rolls.index(min(four_rolls))]
        roll_string = "\n".join([roll_string, f"{stat}: {sum(four_rolls)}"])
        
    return roll_string
    
def get_mythras_roll() -> str:
    roll_string = ""
    for stat in ["STR", "CON", "DEX", "POW", "CHA"]:
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        d3 = random.randint(1, 6)

        roll_string = "\n".join([roll_string, f"{stat}: {d1 + d2 + d3}"])

    for stat in ["INT", "SIZ"]:
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)

        roll_string = "\n".join([roll_string, f"{stat}: {d1 + d2 + 6}"])
        
    return roll_string
    
# Diceroller commmand
def roll_command(update, context):
    dice_roll = parse_diceroll(context.args)
    reply_name = update.message.from_user.username
    
    if dice_roll is None:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f'@{reply_name} please use dice notation, e.g. "3d6 + 2"')
        return
        
    num_dice, num_faces, modifier = dice_roll
    
    if num_dice > 50:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"@{reply_name} can't use more than 50 dice in one roll")
        return
        
    if num_faces > 10000:
        context.bot.send_message(chat_id=update.effective_chat.id, text=f"@{reply_name} can't have more than 10,000 sides on the dice")
        return
    
    total = 0
    rolls = []
    for num in range(num_dice):
        this_roll = random.randint(1, num_faces)
        total += this_roll
        rolls.append(str(this_roll))
    
    roll_result = f"total was {total + modifier} on a {num_dice}d{num_faces}"
    
    if modifier > 0:
        roll_result += f" + {modifier}"
    
    if modifier < 0:
        roll_result += f" - {abs(modifier)}"
    
    if modifier != 0 or len(rolls) > 1:
        roll_result += f" (rolled {', '.join(rolls)})"
        
    context.bot.send_message(chat_id=update.effective_chat.id, text=f"@{reply_name} {roll_result}")

def parse_diceroll(dice_roll) -> list:
    roll_data = re.split("d|(\+)|(-)", "".join(dice_roll), flags=re.IGNORECASE)
    roll_data = [x for x in roll_data if x is not None]
    
    try:
        num_dice = int(roll_data[0])
        num_faces = int(roll_data[1])
        
    except (IndexError, ValueError):
        return None
    
    if num_faces < 1 or num_dice < 1:
        return None
        
    modifier = 0
    
    try:
        if roll_data[2] == '+':
            modifier = int(roll_data[3])
            
        if roll_data[2] == '-':
            modifier = -int(roll_data[3])
            
        
    except (IndexError, ValueError) as e:
        if len(roll_data) != 2 or e is ValueError:
            return None
    
    return [num_dice, num_faces, modifier]