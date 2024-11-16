import os
from flask import Flask, request, render_template, redirect, url_for, flash
from dotenv import load_dotenv
import requests
from flask_sqlalchemy import SQLAlchemy
import logging
from flask_migrate import Migrate 


# Ensure the instance folder exists
if not os.path.exists('instance'):
    os.makedirs('instance')

# Create Flask app
app = Flask(__name__, static_folder='static', instance_relative_config=True)


# Load environment variables
load_dotenv()

# Setting secret key
SECRET_KEY = os.getenv('SECRET_KEY')

# Absolute path to SQLite database in instance folder/ help with chatgpt
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "instance", "games.db")}'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
print(f"Database path: {os.path.join(basedir, 'instance', 'games.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the SQLAlchemy object by passing the Flask app
db = SQLAlchemy(app)

migrate = Migrate(app, db)

# Define the Game model
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    steam_id = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)

    def __repr__(self):
        return f"<Game {self.name}>"

# Define the Wishlist model
class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    game = db.relationship('Game', backref=db.backref('wishlisted', lazy=True))
    target_price = db.Column(db.Float, nullable=True)  # New column for target price

    def __repr__(self):
        game_name = self.game.name if self.game else "Unknown Game"
        return f"<Wishlist Game {game_name}, Target Price {self.target_price}>"

# Log to a file to ensure you can always check the logs
logging.basicConfig(filename='app.log', level=logging.DEBUG, format='%(asctime)s %(message)s')

STEAM_API_KEY = os.getenv('STEAM_API_KEY')  # Make sure your environment variable is correctly set/ help with chatgpt

def get_steam_price_by_name(game_name):
    search_url = f"https://store.steampowered.com/api/storesearch/?term={game_name}&l=english&cc=us"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        search_response = requests.get(search_url, headers=headers, timeout=5)
        search_response.raise_for_status()
        search_results = search_response.json().get('items', [])
        
        matching_games = []
        for game in search_results:
            if all(word in game['name'].lower() for word in game_name.lower().split() if len(word) > 2):
                app_id = game['id']
                price_data = fetch_price_data(app_id, headers)
                if price_data is not None:
                    matching_games.append({
                        'name': game['name'],
                        'appid': app_id,
                        'price': price_data['final'] / 100 if price_data['final'] else 0.0
                    })
        return matching_games
    except requests.RequestException as e:
        logging.error(f"API Request Error for game '{game_name}': {e}")
    return []

def fetch_price_data(app_id, headers):
    try:
        price_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
        price_response = requests.get(price_url, headers=headers, timeout=5)
        price_response.raise_for_status()
        data = price_response.json().get(str(app_id), {}).get('data', {})
        return data.get('price_overview')
    except requests.RequestException as e:
        logging.error(f"Failed to fetch price data for App ID {app_id}: {e}")
    return None


@app.route('/')
def index():
    return render_template('index.html', game=None)

@app.route('/search', methods=['POST'])
def search():
    game_name = request.form.get('game_name')
    logging.debug(f"Search requested for game: {game_name}")

    # Look into the database for games by name (return all matches)
    games = Game.query.filter(Game.name.ilike(f"%{game_name}%")).all()
    logging.debug(f"Database search returned {len(games)} result(s)")

    # If the game is found but you still want to update the data, proceed to fetch from the API/ Help with Chatgpt
    if games:
        logging.debug("Game found in local database, but proceeding to update from Steam API.")
        steam_games = get_steam_price_by_name(game_name)

        if steam_games:
            for steam_game in steam_games:
                existing_game = Game.query.filter_by(steam_id=steam_game['appid']).first()
                if existing_game:
                    # Update the existing game's price with new data from the API
                    existing_game.price = steam_game['price']
                    db.session.commit()
            logging.debug(f"Game '{steam_game['name']}' updated or added to the database with price {steam_game['price']}.")
            return render_template('index.html', games=games)
        else:
            logging.debug(f"No updated results found on Steam API for: {game_name}")
            return render_template('index.html', games=games)
    else:
        logging.debug(f"Game not found in local database. Fetching from Steam API for: {game_name}")
        steam_games = get_steam_price_by_name(game_name)

        if steam_games:
            logging.debug(f"Found {len(steam_games)} game(s) on Steam API, adding to local database.")
            new_games = []
            for steam_game in steam_games:
                existing_game = Game.query.filter_by(steam_id=steam_game['appid']).first()
                if existing_game:
                    logging.debug(f"Game '{steam_game['name']}' already exists in the database. Updating price.")
                    existing_game.price = steam_game['price']
                else:
                    new_game = Game(name=steam_game['name'], steam_id=steam_game['appid'], price=steam_game['price'])
                    db.session.add(new_game)
                    new_games.append(new_game)
            db.session.commit()
            return render_template('index.html', games=new_games)
        else:
            logging.debug(f"No results found on Steam API for: {game_name}")
            return render_template('index.html', games=[])

@app.route('/add_to_wishlist/<int:game_id>', methods=['POST'])
def add_to_wishlist(game_id):
    logging.debug(f"Attempting to add game with ID {game_id} to wishlist.")
    target_price = request.form.get('target_price', type=float)
    game = Game.query.get(game_id)
    
    if game:
        existing_entry = Wishlist.query.filter_by(game_id=game.id).first()
        if not existing_entry:
            new_wishlist_entry = Wishlist(game_id=game.id, target_price=target_price)
            db.session.add(new_wishlist_entry)
            db.session.commit()
            logging.debug(f"Game '{game.name}' added to wishlist with target price {target_price}.")
        else:
            logging.debug(f"Game '{game.name}' is already in the wishlist.")
    else:
        logging.debug(f"Game with ID '{game_id}' not found.")
    
    logging.debug("Redirecting to wishlist page.")
    return redirect(url_for('wishlist'))

@app.route('/delete_from_wishlist/<int:wishlist_id>', methods=['POST'])
def delete_from_wishlist(wishlist_id):
    item = Wishlist.query.get(wishlist_id)
    if item:
        game_name = item.game.name
        db.session.delete(item)
        db.session.commit()
        flash(f"{game_name} has been removed from your wishlist.", "success")
    else:
        flash("Wishlist item not found.", "danger")
    return redirect(url_for('wishlist'))

# Used for logging the requests page 
@app.before_request
def log_request_info():
    logging.debug(f"Request Method: {request.method}, URL: {request.url}")
    if request.method == 'POST':
        logging.debug(f"Form Data: {request.form}")

@app.route('/wishlist', methods=['GET'])
def wishlist():
    try:
        logging.debug("Fetching wishlist items.")
        wishlist_items = Wishlist.query.options(db.joinedload(Wishlist.game)).all()
        logging.info(f"Fetched {len(wishlist_items)} wishlist item(s): {wishlist_items}")
        for item in wishlist_items:
            logging.debug(f"Wishlist Item: {item} - Game: {item.game.name}, Target Price: {item.target_price}")
    except Exception as e:
        logging.error(f"Error fetching wishlist items: {e}")
        wishlist_items = []
    return render_template('wishlist.html', wishlist=wishlist_items, prefill_target_price=False)



@app.route('/update_wishlist_item', methods=['POST'])
def update_wishlist_item():
    logging.debug(f"Request method: {request.method}")
    logging.debug(f"Request URL: {request.url}")
    logging.debug(f"Request form data: {request.form}")
    
    # Extract form data
    wishlist_id = request.form.get('wishlist_id', type=int)
    new_target_price = request.form.get('target_price', type=float)
    logging.info(f"Attempting to update wishlist item ID {wishlist_id} to target price {new_target_price}.")

    if not wishlist_id or new_target_price is None:
        logging.error("Invalid form data received.")
        flash("Invalid form submission.", "danger")
        return redirect(url_for('wishlist'))

    # Fetch wishlist item from DB
    item = Wishlist.query.get(wishlist_id)
    if item:
        logging.debug(f"Found wishlist item: {item}")
        item.target_price = new_target_price
        db.session.commit()
        logging.info(f"Successfully updated target price for {item.game.name} to ${new_target_price:.2f}.")
        flash(f"Updated target price for {item.game.name} to ${new_target_price:.2f}.", "success")
    else:
        logging.warning(f"No wishlist item found with ID {wishlist_id}.")
        flash("Wishlist item not found.", "danger")
    
    return redirect(url_for('wishlist'))

if __name__ == '__main__':
    with app.app_context():
        print("Creating all tables...")
        try:
            db.create_all()
            print("Tables created successfully.")
        except Exception as e:
            print(f"Error during table creation: {e}")
    app.run(debug=True)
