from time import time
from hashlib import sha256
import json
from uuid import uuid4
from flask import Flask, jsonify, request
import requests
from urllib.parse import urlparse

class Blockchain:
	def __init__(self):
		'''
			Initializes the following -
				current_transactions: List of the transactions to be mined in the next block
							   chain: The actual blockchain list holding all the blocks
							   nodes: Set of nodes (peers)
						 add_block(): Adds the genesis block with random previous_hash and proof
						 			  (Thereby the genesis block won't verify but it would be same for all)
		'''
		self.current_transactions = []
		self.chain = []
		self.add_block(previous_hash='secret', proof=42)
		self.nodes = set()

	def register_node(self, address):
		'''
			Parameters -
				address: URL of the participating nodes

			Adds the participating node's URL to the blockchain nodes set
		'''
		parsed_url = urlparse(address)
		if parsed_url.netloc:
			self.nodes.add(parsed_url.netloc)
		elif parsed_url.path:
			self.nodes.add(parsed_url.path)
		else:
			raise ValueError('URL Invalid!')

	def valid_chain(self, chain):
		'''
			Parameters -
				chain: One of the chains to be validated for correctness

			Returns -
				True if the chain is valid else False 
		'''
		last_block = chain[0]
		current_index = 1
		while current_index < len(chain):
			block = chain[current_index]
			last_block_hash = self.hash(last_block)
			if block['previous_hash'] != last_block_hash:
				return False

			if not self.validate(last_block['proof'], block['proof'], last_block_hash):
				return False

			last_block = block
			current_index += 1

		return True

	def resolve_conflicts(self):
		'''
			Resolves conflicts in the blockchain with different nodes having different blockchain versions
			Changes the blockchain if there is another version whose length is more and is valid

			Returns -
				True if there was conflict which got resolved else False if there was no conflict at all
		'''
		neighbors = self.nodes
		new_chain = None
		max_length = len(self.chain)

		for node in neighbors:
			url = f'http://{node}/chain'
			response = requests.get(url)

			if response.status_code == 200:
				length = response.json()['length']
				chain = response.json()['chain']

				if length > max_length and self.valid_chain(chain):
					max_length = length
					new_chain = chain

		if new_chain:
			self.chain = new_chain
			return True

		return False

	@property
	def last_block(self):
		'''
			Returns -
				Last block of the blockchain
		'''
		return self.chain[-1]

	@staticmethod
	def hash(block):
		'''
			Returns - 
				The sha256 hash of the parameter block converted to json string
		'''
		block_string = json.dumps(block, sort_keys=True).encode()
		# encode() converts to utf-8
		# sort_keys to avoid inconsistencies, since in dict the order doesn't matter, but here we need order
		
		return sha256(block_string).hexdigest()

	def new_transaction(self, sender, recipient, amount):
		'''
			Parameters - 
				   sender: The id of the user who is sending the amount
				recipient: The id of the user who is receiving the amount
				   amount: The amount of coins to be transferred from sender to recipient

			Adds a new transaction to the current_transactions pool

			Returns -
				The index of the block where this particular transaction would be added 
				(The next block index of the blockchain)
		'''
		tx = {
			'sender':sender, 
			'recipient':recipient, 
			'amount':amount 
		}
		self.current_transactions.append(tx)

		return self.last_block['index'] + 1

	def add_block(self, proof, previous_hash):
		'''
			Parameters -
						proof: Proof (Nonce) obtained from the Proof of Work algorithm for the current block
				previous_hash: Hash of the previous block which is the latest block in the blockchain for now

			Includes all the transactions from the transaction pool in the current block
			Clears the transaction pool
			Adds the block to the blockchain

			Returns -
				The newly created (mined) block
		'''
		block = {
			'index': len(self.chain) + 1,
			'timestamp': time(),
			'transactions': self.current_transactions,
			'proof': proof,
			'previous_hash': previous_hash or self.hash(self.chain[-1])
		}
		self.current_transactions = []
		self.chain.append(block)

		return block

	@staticmethod
	def validate(last_proof, proof, last_hash, difficulty=4):
		'''
			Parameters -
				last_proof: Proof (nonce) of the previous block
					 proof: Proof (nonce) of the block to be validated
				 last_hash: Hash of the previous block
				difficulty: The number of zeros needed in a hash to agree upon the proof of work (default = 4)

			Finds the sha256 hash of the first three parameters concatenated

			Returns - 
				True if the obtained hash begins with the difficulty number of zeros else False
		'''
		guess = f'{last_proof}{proof}{last_hash}'.encode()
		guess_hash = sha256(guess).hexdigest()

		return guess_hash[:difficulty] == '0' * difficulty

	def proof_of_work(self, last_block):
		'''
			Parameters -
				last_block: The current block in the blockchain

			Extracts the proof and hash from the last_block
			Finds the proof (nonce) which validates (as per the above function)

			Returns -
				The proof (nonce) obtained for the block
		'''
		last_proof = last_block['proof']
		last_hash = self.hash(last_block)
		proof = 0
		while not (self.validate(last_proof, proof, last_hash)):
			proof += 1

		return proof

# Initialize the Flask app
app = Flask(__name__)

# uuid identifier for each node after removal of '-'
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the blockchain
blockchain = Blockchain()


@app.route('/chain', methods=['GET'])
def full_chain():
	'''
		Displays the full blockchain in JSON format 
	'''
	response = {
		'chain': blockchain.chain,
		'length': len(blockchain.chain)
	}
	return jsonify(response), 200  # 200 implies a good request

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
	'''
		Adds a transaction to the transaction pool and returns the block number where it would be added
	'''
	values = request.get_json(force=True)
	required = ['sender', 'recipient', 'amount']
	
	if not all(k in values for k in required):
		return 'Missing values', 400

	sender = values['sender']
	recipient = values['recipient']
	amount = values['amount']

	index = blockchain.new_transaction(sender, recipient, amount)
	response = {
		'message': f'Block #{index}'
	}
	return jsonify(response), 201

@app.route('/mine', methods=['GET'])
def mine():
	'''
		Mines a new block with the same sender, recipient and amount always
	'''
	last_block = blockchain.last_block
	proof = blockchain.proof_of_work(last_block)

	blockchain.new_transaction('0', node_identifier, 20)
	previous_hash = blockchain.hash(last_block)
	block = blockchain.add_block(proof, previous_hash)

	response = {
		'message': 'New block was mined!',
		'index': block['index'],
		'proof': block['proof'],
		'transactions': block['transactions'],
		'previous_hash': block['previous_hash']
	}

	return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
	'''
		Registers the nodes to the set of nodes for a blockchain
	'''
	values = json.loads(requests.data)
	nodes = values.get('nodes')
	if nodes is None:
		return 'Error', 400
	for node in nodes:
		blockchain.register_node('http://1227.0.0.1:' + str(node))
	response = {
		'message': 'Added new nodes',
		'node_list': list(blockchain.nodes)
	}
	return jsonify(response), 200

@app.route('/nodes/resolve', methods=['GET'])
def consensus():
	'''
		Resolves conflicts if any are happening and gives a propoer message
	'''
	replaced = blockchain.resolve_conflicts()
	if replaced:
		response = {
			'message': 'Blockchain was replaced!',
			'new_chain': blockchain.chain
		}
	else:
		response = {
			'message': 'No change!'
		}
	return jsonify(response), 200

if __name__ == '__main__':
	# To add an user-defined argument to specify port number at runtime
	from argparse import ArgumentParser

	# Node identifier would be the uuid created for the port where the code is running
	print(node_identifier)

	parser = ArgumentParser()
	parser.add_argument('-p', '--port', type=int, default=5000, help='port number')
	port = parser.parse_args().port

	# Run the app on the localhost and on the specified port in debug mode
	app.run(host='127.0.0.1', port=port, debug=True)