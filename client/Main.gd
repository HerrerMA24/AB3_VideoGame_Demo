extends Node

# Imports
const NetworkClient = preload("res://websockets_client.gd")
const Packet = preload("res://packet.gd")
const Chatbox = preload("res://Chatbox.tscn")
const Actor = preload("res://Actor.tscn")

onready var _network_client = NetworkClient.new()
onready var _login_screen = get_node("Login")
var _chatbox = null
var state: FuncRef
var _username: String
var _actors: Dictionary = {}
var _player_actor = null
var _world_items: Dictionary = {}
var _inventory: Array = []


func _ready():
	_network_client.connect("connected", self, "_handle_client_connected")
	_network_client.connect("disconnected", self, "_handle_client_disconnected")
	_network_client.connect("error", self, "_handle_network_error")
	_network_client.connect("data", self, "_handle_network_data")
	add_child(_network_client)
	_network_client.connect_to_server("127.0.0.1", 8081)
	
	_login_screen.connect("login", self, "_handle_login_button")
	_login_screen.connect("register", self, "_handle_register_button")
	state = null

func LOGIN(p):
	match p.action:
		"Ok":
			_enter_game()
		"Deny":
			var reason: String = p.payloads[0]
			OS.alert(reason)

func REGISTER(p):
	match p.action:
		"Ok":
			OS.alert("Registration successful")
		"Deny":
			var reason: String = p.payloads[0]
			OS.alert(reason)

func PLAY(p):
	match p.action:
		"ModelDelta":
			var model_data: Dictionary = p.payloads[0]
			_update_models(model_data)
		"Chat":
			var username: String = p.payloads[0]
			var message: String = p.payloads[1]
			_chatbox.add_message(username, message)
			
		"Disconnect":
			var actor_id: int = p.payloads[0]
			var actor = _actors[actor_id]
			_chatbox.add_message(null, actor.actor_name + " has disconnected.")
			remove_child(actor)
			_actors.erase(actor_id)
			
		"ItemSpawn":
			var item_data: Dictionary = p.payloads[0]
			_spawn_world_item(item_data)
			
		"ItemRemove":
			var item_id: int = p.payloads[0]
			_remove_world_item(item_id)
			
		"Inventory":
			var inventory_data: Array = p.payloads[0]
			_update_inventory(inventory_data)
			
	
func _handle_login_button(username: String, password: String):
	state = funcref(self, "LOGIN")
	var p: Packet = Packet.new("Login", [username, password])
	_network_client.send_packet(p)
	_username = username

func _handle_register_button(username: String, password: String, avatar_id: int):
	state = funcref(self, "REGISTER")
	var p: Packet = Packet.new("Register", [username, password, avatar_id])
	_network_client.send_packet(p)
	

func _update_models(model_data: Dictionary):
	"""
	Runs a function with signature 
	`_update_x(model_id: int, model_data: Dictionary)` where `x` is the name 
	of a model (e.g. `_update_actor`).
	"""
	print("Received model data: %s" % JSON.print(model_data))
	var model_id: int = model_data["id"]
	var func_name: String = "_update_" + model_data["model_type"].to_lower()
	var f: FuncRef = funcref(self, func_name)
	f.call_func(model_id, model_data)

func _update_actor(model_id: int, model_data: Dictionary):
	# If this is an existing actor, just update them
	if model_id in _actors:
		_actors[model_id].update(model_data)

	# If this actor doesn't exist in the game yet, create them
	else:
		var new_actor
		
		if not _player_actor: 
			_player_actor = Actor.instance().init(model_data)
			_player_actor.is_player = true
			new_actor = _player_actor
		else:
			new_actor = Actor.instance().init(model_data)
		
		_actors[model_id] = new_actor
		add_child(new_actor)

func _enter_game():
	state = funcref(self, "PLAY")

	# Remove the login screen
	remove_child(_login_screen)

	# Instance the chatbox
	_chatbox = Chatbox.instance()
	_chatbox.connect("message_sent", self, "send_chat")
	add_child(_chatbox)
	
func send_chat(text: String):
	var p: Packet = Packet.new("Chat", [_username, text])
	_network_client.send_packet(p)
	_chatbox.add_message(_username, text)

func _handle_client_connected():
	print("Client connected to server!")


func _handle_client_disconnected(was_clean: bool):
	OS.alert("Disconnected %s" % ["cleanly" if was_clean else "unexpectedly"])
	get_tree().quit()


func _handle_network_data(data: String):
	print("Received server data: ", data)
	var action_payloads: Array = Packet.json_to_action_payloads(data)
	var p: Packet = Packet.new(action_payloads[0], action_payloads[1])
	print("Parsed packet action: ", p.action)
	if p.action == "ItemRemove":
		print("*** ITEMREMOVE PACKET DETECTED ***")
		print("Payloads: ", p.payloads)
	# Pass the packet to our current state
	state.call_func(p)


func _handle_network_error():
	OS.alert("There was an error")

func _show_pickup_message(text: String):
	# Create a temporary label for pickup notification
	var pickup_label = Label.new()
	pickup_label.text = text
	pickup_label.add_color_override("font_color", Color.green)
	pickup_label.rect_position = Vector2(400, 100)
	pickup_label.rect_size = Vector2(300, 50)
	pickup_label.align = Label.ALIGN_CENTER
	add_child(pickup_label)
	
	# Create tween to fade out the message
	var tween = Tween.new()
	add_child(tween)
	tween.interpolate_property(pickup_label, "modulate:a", 1.0, 0.0, 2.0)
	tween.start()
	
	# Remove the label after animation
	yield(tween, "tween_completed")
	remove_child(pickup_label)
	pickup_label.queue_free()
	remove_child(tween)
	tween.queue_free()

func _spawn_world_item(item_data: Dictionary):
	var item_id = int(item_data["id"])  # Ensure integer type
	var x = item_data["x"]
	var y = item_data["y"]
	var item_name = item_data["item"]["name"]
	var item_type = item_data["item"]["item_type"]
	
	# Create colored circle for item
	var item_node = Control.new()
	item_node.rect_size = Vector2(20, 20)
	item_node.rect_position = Vector2(x - 10, y - 10)
	item_node.name = "WorldItem_" + str(item_id)
	
	# Add circle shape
	var circle = ColorRect.new()
	circle.rect_size = Vector2(20, 20)
	circle.rect_position = Vector2(0, 0)
	
	# Set different colors based on item type
	if item_type == "weapon":
		circle.color = Color.yellow
	elif item_type == "potion":
		circle.color = Color.red
	else:
		circle.color = Color.white
	
	item_node.add_child(circle)
	
	# Add label
	var label = Label.new()
	label.text = item_name
	label.rect_position = Vector2(-20, -30)
	label.rect_size = Vector2(40, 15)
	label.align = Label.ALIGN_CENTER
	item_node.add_child(label)
	
	add_child(item_node)
	_world_items[item_id] = item_node
	
	print("Spawned item: ", item_name, " at ", x, ", ", y)

func _remove_world_item(item_id: int):
	var id = int(item_id)
	
	if _world_items.has(id):
		var item_node = _world_items[id]
		item_node.visible = false
		remove_child(item_node)
		item_node.queue_free()
		_world_items.erase(id)
		_show_pickup_message("Item added to inventory!")

var _last_inventory_count = 0

func _update_inventory(inventory_data: Array):
	_inventory = inventory_data
	print("Inventory updated: ")
	
	for item in inventory_data:
		print("  ", item["item"]["name"], " x", item["quantity"])
	
	_last_inventory_count = inventory_data.size()

func _show_inventory_display():
	# Request fresh inventory data from server/RDS
	var p: Packet = Packet.new("InventoryRequest", [])
	_network_client.send_packet(p)
	
	# Create inventory panel
	var inventory_panel = ColorRect.new()
	inventory_panel.color = Color(0, 0, 0, 0.8)
	inventory_panel.rect_position = Vector2(50, 50)
	inventory_panel.rect_size = Vector2(300, 200)
	
	# Add title
	var title = Label.new()
	title.text = "INVENTORY (from RDS)"
	title.add_color_override("font_color", Color.white)
	title.rect_position = Vector2(10, 10)
	title.rect_size = Vector2(280, 30)
	title.align = Label.ALIGN_CENTER
	inventory_panel.add_child(title)
	
	# Add inventory items
	var y_offset = 50
	if _inventory.size() == 0:
		var empty_label = Label.new()
		empty_label.text = "Inventory is empty"
		empty_label.add_color_override("font_color", Color.gray)
		empty_label.rect_position = Vector2(10, y_offset)
		empty_label.rect_size = Vector2(280, 20)
		empty_label.align = Label.ALIGN_CENTER
		inventory_panel.add_child(empty_label)
	else:
		for item in _inventory:
			var item_label = Label.new()
			item_label.text = item["item"]["name"] + " x" + str(item["quantity"])
			item_label.add_color_override("font_color", Color.white)
			item_label.rect_position = Vector2(20, y_offset)
			item_label.rect_size = Vector2(260, 20)
			inventory_panel.add_child(item_label)
			y_offset += 25
	
	add_child(inventory_panel)
	
	# Auto-remove after 5 seconds
	var timer = Timer.new()
	timer.wait_time = 5.0
	timer.one_shot = true
	timer.connect("timeout", self, "_remove_inventory_display", [inventory_panel, timer])
	add_child(timer)
	timer.start()

func _remove_inventory_display(panel, timer):
	remove_child(panel)
	panel.queue_free()
	remove_child(timer)
	timer.queue_free()

func _try_pickup_nearby_item():
	if not _player_actor:
		return
	
	var player_pos = _player_actor.body.position
	var pickup_range = 50
	
	print("=== PICKUP ATTEMPT ===")
	print("Player position: ", player_pos)
	print("Available items: ", _world_items.keys())
	
	# Find closest item within range
	var closest_item_id = -1
	var closest_distance = pickup_range + 1
	
	for item_id in _world_items:
		var item_node = _world_items[item_id]
		var item_pos = item_node.rect_position + Vector2(10, 10)  # Center of item
		var distance = player_pos.distance_to(item_pos)
		print("Item ", item_id, " at ", item_pos, " distance: ", distance)
		
		if distance < closest_distance:
			closest_distance = distance
			closest_item_id = item_id
	
	if closest_item_id != -1:
		print("Closest item: ", closest_item_id, " at distance: ", closest_distance)
		# Only send pickup if item still exists in our world
		if closest_item_id in _world_items:
			var p: Packet = Packet.new("Pickup", [closest_item_id])
			_network_client.send_packet(p)
			print("Sent pickup packet for item: ", closest_item_id)
		else:
			print("Item already removed from world")
	else:
		print("No items nearby to pickup (range: ", pickup_range, ")")
	print("=== END PICKUP ===")

	
func _unhandled_input(event: InputEvent):
	if _player_actor and event.is_action_released("click"):
		var target = _player_actor.body.get_global_mouse_position()
		_player_actor._player_target = target
		var p: Packet = Packet.new("Target", [target.x, target.y])
		_network_client.send_packet(p)
	
	if event.is_action_pressed("ui_accept"):  # Space bar
		_try_pickup_nearby_item()
	
	if event is InputEventKey and event.pressed and event.scancode == KEY_I:
		_show_inventory_display()
