import boto3
import json
from botocore.exceptions import ClientError
import os
import math
import utils
import queue
import time
import hmac
import hashlib
import base64
from pathlib import Path
from server import packet
from server import models
from server.secrets import get_config
from autobahn.twisted.websocket import WebSocketServerProtocol
from autobahn.exception import Disconnected

# Get configuration from Secrets Manager
config = get_config()

class GameServerProtocol(WebSocketServerProtocol):
    def __init__(self):
        super().__init__()
        self._packet_queue: queue.Queue[tuple['GameServerProtocol', packet.Packet]] = queue.Queue()
        self._state: callable = self.LOGIN
        self._actor: models.Actor = None
        self._player_target: list = None
        self._last_delta_time_checked = None
        self._known_others: set['GameServerProtocol'] = set()
        self._cognito_client = boto3.client('cognito-idp', region_name=config['AWS_DEFAULT_REGION'])
        self._client_secret = config['AWS_COGNITO_CLIENT_SECRET']
        self._client_id = config['AWS_COGNITO_CLIENT_ID']
        self._last_item_spawn = 0
    
    def _get_secret_hash(self, username: str) -> str:
        """Generate SECRET_HASH for Cognito authentication"""
        message = username + self._client_id
        dig = hmac.new(
            self._client_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(dig).decode()

    def LOGIN(self, sender: 'GameServerProtocol', p: packet.Packet):
        print(f"Processing LOGIN packet: {p.action}")
        
        if p.action == packet.Action.Login:
            print("Starting login process...")
            username, password = p.payloads
            print(f"User: {username}")
            try:
                print("Calling Cognito for login...")
                response = self._cognito_client.admin_initiate_auth(
                    UserPoolId=config['AWS_COGNITO_USER_POOL_ID'],
                    ClientId=config['AWS_COGNITO_CLIENT_ID'],
                    AuthFlow='ADMIN_NO_SRP_AUTH',
                    AuthParameters={
                        'USERNAME': username,
                        'PASSWORD': password,
                        'SECRET_HASH': self._get_secret_hash(username)
                    }
                )
                print("Cognito login successful")
                
                user, created = models.User.objects.get_or_create(
                    username=username,
                    defaults={'cognito_user_id': username}
                )
                
                try:
                    self._actor = models.Actor.objects.get(user=user)
                    print("Actor found for user")
                except models.Actor.DoesNotExist:
                    print("No actor found for user")
                    self.send_client(packet.DenyPacket("No character found for this user"))
                    return
                
                self.send_client(packet.OkPacket())
                self.broadcast(packet.ModelDeltaPacket(models.create_dict(self._actor)))
                self._state = self.PLAY
                
                # Send existing world items to player
                world_items = models.WorldItem.objects.all()
                for world_item in world_items:
                    self.send_client(packet.ItemSpawnPacket(models.create_dict(world_item)))
                
                # Send current inventory
                self._send_inventory()
                
                # Spawn test items (only once)
                self._spawn_test_items()
                
                print("Login completed successfully")
                
            except ClientError as e:
                print(f"Login error: {e}")
                self.send_client(packet.DenyPacket("Invalid username or password"))
            except Exception as e:
                print(f"Unexpected login error: {e}")
                self.send_client(packet.DenyPacket(f"Login failed: {str(e)}"))

        elif p.action == packet.Action.Register:
            print("Starting registration process...")
            username, password, avatar_id = p.payloads
            print(f"User: {username}, Avatar: {avatar_id}")
            try:
                print("Calling Cognito for registration...")
                self._cognito_client.admin_create_user(
                    UserPoolId=config['AWS_COGNITO_USER_POOL_ID'],
                    Username=username,
                    TemporaryPassword=password,
                    MessageAction='SUPPRESS'
                )
                print("Cognito user created")
                
                self._cognito_client.admin_set_user_password(
                    UserPoolId=config['AWS_COGNITO_USER_POOL_ID'],
                    Username=username,
                    Password=password,
                    Permanent=True
                )
                print("Cognito password set")
                
                print("Creating database records...")
                try:
                    user = models.User(username=username, cognito_user_id=username)
                    user.save()
                    print("User saved")
                    player_entity = models.Entity(name=username)
                    player_entity.save()
                    print("Entity saved")
                    player_ientity = models.InstancedEntity(entity=player_entity, x=0, y=0)
                    player_ientity.save()
                    print("InstancedEntity saved")
                    player = models.Actor(instanced_entity=player_ientity, user=user, avatar_id=avatar_id)
                    player.save()
                    print("Actor saved")
                    print("Database records created")
                except Exception as db_error:
                    print(f"Database error: {db_error}")
                    raise db_error
                
                self.send_client(packet.OkPacket())
                print("Registration completed successfully")
                
            except ClientError as e:
                print(f"Cognito error: {e}")
                if e.response['Error']['Code'] == 'UsernameExistsException':
                    self.send_client(packet.DenyPacket("This username is already taken"))
                else:
                    self.send_client(packet.DenyPacket("Registration failed"))
            except Exception as e:
                print(f"Unexpected registration error: {e}")
                self.send_client(packet.DenyPacket(f"Registration failed: {str(e)}"))




    # amazonq-ignore-next-line
    def PLAY(self, sender: 'GameServerProtocol', p: packet.Packet):
        if p.action == packet.Action.Chat:
            if sender == self:
                self.broadcast(p, exclude_self=True)
            else:
                self.send_client(p)
        
        elif p.action == packet.Action.ModelDelta:
            self.send_client(p)
            if sender not in self._known_others:
                # Send our full model data to the new player
                sender.onPacket(self, packet.ModelDeltaPacket(models.create_dict(self._actor)))
                self._known_others.add(sender)
                
        elif p.action == packet.Action.Target:
            self._player_target = p.payloads
        
        elif p.action == packet.Action.Pickup:
            item_id = p.payloads[0]
            self._handle_pickup(item_id)
        
        elif p.action == packet.Action.InventoryRequest:
            self._send_inventory()

        elif p.action == packet.Action.Disconnect:
            # amazonq-ignore-next-line
            self._known_others.discard(sender)
            self.send_client(p)

    def _update_position(self) -> bool:
        "Attempt to update the actor's position and return true only if the position was changed"
        if not self._player_target:
            return False
        pos = [self._actor.instanced_entity.x, self._actor.instanced_entity.y]

        now: float = time.time()
        delta_time: float = 1 / self.factory.tickrate
        if self._last_delta_time_checked:
            delta_time = now - self._last_delta_time_checked
        self._last_delta_time_checked = now

        # Use delta time to calculate distance to travel this time
        dist: float = 70 * delta_time
        
        # Early exit if we are already within an acceptable distance of the target
        if math.dist(pos, self._player_target) < dist:
            return False
        
        # Update our model if we're not already close enough to the target
        d_x, d_y = utils.direction_to(pos, self._player_target)
        self._actor.instanced_entity.x += d_x * dist
        self._actor.instanced_entity.y += d_y * dist
        # amazonq-ignore-next-line
        self._actor.instanced_entity.save()

        return True
    
    def _check_item_respawn(self):
        """Check if items need to respawn every 20 seconds"""
        current_time = time.time()
        time_since_last_spawn = current_time - self._last_item_spawn
        
        if time_since_last_spawn >= 20:  # Back to 20 seconds
            self._last_item_spawn = current_time
            
            # Get item types that should exist
            sword_item = models.Item.objects.filter(name="Iron Sword").first()
            potion_item = models.Item.objects.filter(name="Health Potion").first()
            
            sword_exists = models.WorldItem.objects.filter(item=sword_item).exists() if sword_item else False
            potion_exists = models.WorldItem.objects.filter(item=potion_item).exists() if potion_item else False
            
            if sword_item and not sword_exists:
                world_sword = models.WorldItem.objects.create(item=sword_item, x=100, y=150)
                self.broadcast(packet.ItemSpawnPacket(models.create_dict(world_sword)))
                print("Respawned Iron Sword at (100,150)")
            
            if potion_item and not potion_exists:
                world_potion = models.WorldItem.objects.create(item=potion_item, x=150, y=100)
                self.broadcast(packet.ItemSpawnPacket(models.create_dict(world_potion)))
                print("Respawned Health Potion at (150,100)")
    
    def _handle_pickup(self, item_id: int):
        """Handle item pickup by player"""
        try:
            # Find the world item
            world_item = models.WorldItem.objects.get(id=item_id)
            
            # Check if item is close enough to player
            player_x = self._actor.instanced_entity.x
            player_y = self._actor.instanced_entity.y
            item_x = world_item.x
            item_y = world_item.y
            
            distance = ((player_x - item_x) ** 2 + (player_y - item_y) ** 2) ** 0.5
            
            if distance <= 50:  # Pickup range
                # Add to inventory or increase quantity
                inventory_item, created = models.Inventory.objects.get_or_create(
                    actor=self._actor,
                    item=world_item.item,
                    defaults={'quantity': 1}
                )
                
                if not created:
                    inventory_item.quantity += 1
                    inventory_item.save()
                
                # Remove from world
                world_item.delete()
                
                # Notify all players item was removed (including self)
                self.broadcast(packet.ItemRemovePacket(item_id))
                # Also send to self since broadcast might exclude self
                self.send_client(packet.ItemRemovePacket(item_id))
                
                # Send updated inventory to player
                self._send_inventory()
                
                print(f"Player {self._actor.user.username} picked up {world_item.item.name}")
            else:
                print(f"Item too far away: {distance}")
                
        except models.WorldItem.DoesNotExist:
            print(f"World item {item_id} not found")
    
    def _send_inventory(self):
        """Send current inventory to player"""
        inventory_items = models.Inventory.objects.filter(actor=self._actor)
        inventory_data = []
        
        for inv_item in inventory_items:
            item_dict = models.create_dict(inv_item)
            inventory_data.append(item_dict)
        
        self.send_client(packet.InventoryPacket(inventory_data))
    
    def _spawn_test_items(self):
        """Spawn some test items in the world"""
        # Create test items if they don't exist
        sword, created = models.Item.objects.get_or_create(
            name="Iron Sword",
            defaults={'description': "A sturdy iron sword", 'item_type': "weapon"}
        )
        
        potion, created = models.Item.objects.get_or_create(
            name="Health Potion",
            defaults={'description': "Restores health", 'item_type': "potion"}
        )
        
        # Only spawn if items don't already exist at these locations
        if not models.WorldItem.objects.filter(item=sword, x=100, y=150).exists():
            world_sword = models.WorldItem.objects.create(item=sword, x=100, y=150)
            self.broadcast(packet.ItemSpawnPacket(models.create_dict(world_sword)))
            print(f"Spawned sword at (100,150)")
        
        if not models.WorldItem.objects.filter(item=potion, x=150, y=100).exists():
            world_potion = models.WorldItem.objects.create(item=potion, x=150, y=100)
            self.broadcast(packet.ItemSpawnPacket(models.create_dict(world_potion)))
            print(f"Spawned potion at (150,100)")

    def tick(self):
        # Process the next packet in the queue
        if not self._packet_queue.empty():
            print(f"Processing packet from queue, queue size: {self._packet_queue.qsize()}")
            s, p = self._packet_queue.get()
            print(f"Calling state function: {self._state.__name__} with packet: {p.action}")
            self._state(s, p)

        # To do when there are no packets to process
        elif self._state == self.PLAY: 
            # amazonq-ignore-next-line
            actor_dict_before: dict = models.create_dict(self._actor)
            if self._update_position():
                actor_dict_after: dict = models.create_dict(self._actor)
                self.broadcast(packet.ModelDeltaPacket(models.get_delta_dict(actor_dict_before, actor_dict_after)))
            
            # Check if items need to respawn
            self._check_item_respawn()


    def broadcast(self, p: packet.Packet, exclude_self: bool = False):
        for other in self.factory.players:
            if other == self and exclude_self:
                continue
            other.onPacket(self, p)

    # Override
    def onConnect(self, request):
        print(f"Client connecting: {request.peer}")

    # Override
    def onOpen(self):
        print(f"Websocket connection open.")

    # Override
    def onClose(self, wasClean, code, reason):
        if self._actor:
            self._actor.save()
            self.broadcast(packet.DisconnectPacket(self._actor.id), exclude_self=True)
        self.factory.players.remove(self)
        print(f"Websocket connection closed{' unexpectedly' if not wasClean else ' cleanly'} with code {code}: {reason}")

    # Override
    def onMessage(self, payload, isBinary):
        # amazonq-ignore-next-line
        decoded_payload = payload.decode('utf-8')

        # amazonq-ignore-next-line
        try:
            p: packet.Packet = packet.from_json(decoded_payload)
        except Exception as e:
            print(f"Could not load message as packet: {e}. Message was: {payload.decode('utf-8')}")
            return

        self.onPacket(self, p)

    def onPacket(self, sender: 'GameServerProtocol', p: packet.Packet):
        self._packet_queue.put((sender, p))
        # amazonq-ignore-next-line
        print(f"Queued packet: {p}")
        print(f"Current state: {self._state.__name__ if self._state else 'None'}")
        print(f"Queue size after adding: {self._packet_queue.qsize()}")

    def send_client(self, p: packet.Packet):
        b = bytes(p)
        try:
            self.sendMessage(b)
        except Disconnected:
            print(f"Couldn't send {p} because client disconnected.")


