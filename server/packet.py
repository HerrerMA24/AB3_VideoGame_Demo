import json
import enum


class Action(enum.Enum):
    Ok = enum.auto()
    Deny = enum.auto()
    Disconnect = enum.auto()
    Login = enum.auto()
    Register = enum.auto()
    Chat = enum.auto()
    ModelDelta = enum.auto()
    Target = enum.auto()
    Pickup = enum.auto()
    ItemSpawn = enum.auto()
    ItemRemove = enum.auto()
    Inventory = enum.auto()
    InventoryRequest = enum.auto()


class Packet:
    def __init__(self, action: Action, *payloads):
        self.action: Action = action
        self.payloads: tuple = payloads

    def __str__(self) -> str:
        serialize_dict = {'a': self.action.name}
        for i in range(len(self.payloads)):
            serialize_dict[f'p{i}'] = self.payloads[i]
        data = json.dumps(serialize_dict, separators=(',', ':'))
        return data

    def __bytes__(self) -> bytes:
        return str(self).encode('utf-8')

class OkPacket(Packet):
    def __init__(self):
        super().__init__(Action.Ok)

class DenyPacket(Packet):
    def __init__(self, reason: str):
        super().__init__(Action.Deny, reason)

class DisconnectPacket(Packet):
    def __init__(self, actor_id: int):
        super().__init__(Action.Disconnect, actor_id)

class LoginPacket(Packet):
    def __init__(self, username: str, password: str):
        super().__init__(Action.Login, username, password)

class RegisterPacket(Packet):
    def __init__(self, username: str, password: str, avatar_id: int):
        super().__init__(Action.Register, username, password, avatar_id)

class ChatPacket(Packet):
    def __init__(self, sender: str, message: str):
        super().__init__(Action.Chat, sender, message)

class ModelDeltaPacket(Packet):
    def __init__(self, model_data: dict):
        super().__init__(Action.ModelDelta, model_data)

class TargetPacket(Packet):
    def __init__(self, t_x: float, t_y: float):
        super().__init__(Action.Target, t_x, t_y)

class PickupPacket(Packet):
    def __init__(self, item_id: int):
        super().__init__(Action.Pickup, item_id)

class ItemSpawnPacket(Packet):
    def __init__(self, item_data: dict):
        super().__init__(Action.ItemSpawn, item_data)

class ItemRemovePacket(Packet):
    def __init__(self, item_id: int):
        super().__init__(Action.ItemRemove, item_id)

class InventoryPacket(Packet):
    def __init__(self, inventory_data: list):
        super().__init__(Action.Inventory, inventory_data)

class InventoryRequestPacket(Packet):
    def __init__(self):
        super().__init__(Action.InventoryRequest)


def from_json(json_str: str) -> Packet:
    obj_dict = json.loads(json_str)

    action = None
    payloads = []
    for key, value in obj_dict.items():
        if key == 'a':
            action = value

        elif key[0] == 'p':
            index = int(key[1:])
            payloads.insert(index, value)

    # Use reflection to construct the specific packet type we're looking for
    class_name = action + "Packet"
    try:
        constructor: type = globals()[class_name]
        return constructor(*payloads)
    except KeyError as e:
        print(
            f"{class_name} is not a valid packet name. Stacktrace: {e}")
    except TypeError:
        print(
            f"{class_name} can't handle arguments {tuple(payloads)}.")
