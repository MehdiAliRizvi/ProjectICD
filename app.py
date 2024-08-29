from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from pymongo import MongoClient

class Rule:
    def __init__(self, parameter, min_value, max_value, unit, age_range, gender, valid_until, first_condition=None):
        self.parameter = parameter
        self.min_value = min_value
        self.max_value = max_value
        self.unit = unit
        self.age_range = age_range
        self.gender = gender
        self.valid_until = valid_until
        self.first_condition = first_condition

    def to_dict(self):
        return {
            'parameter': self.parameter,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'unit': self.unit,
            'age_range': self.age_range,
            'gender': self.gender,
            'valid_until': self.valid_until,
            'first_condition': self.first_condition
        }

class Disease:
    def __init__(self, disease_code, disease_name, rules):
        self.disease_code = disease_code
        self.disease_name = disease_name
        self.rules = rules

    def to_dict(self):
        return {
            'disease_code': self.disease_code,
            'disease_name': self.disease_name,
            'rules': [rule.to_dict() for rule in self.rules]
        }

class Database:
    def __init__(self, uri, db_name, rulebase_collection_name, user_input_collection_name, parameters_collection_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.rulebase_collection = self.db[rulebase_collection_name]
        self.user_input_collection = self.db[user_input_collection_name]
        self.parameters_collection = self.db[parameters_collection_name]  # Collection for parameters

    def insert_disease(self, disease):
        existing_disease = self.rulebase_collection.find_one({'disease_code': disease.disease_code})
        if existing_disease:
            return 'Error: A disease with this code already exists!'
        
        try:
            self.rulebase_collection.insert_one(disease.to_dict())
            return 'Data submitted successfully!'
        except Exception as e:
            return f'Error inserting data: {e}'

    def insert_lab_values(self, lab_values):
        try:
            self.user_input_collection.insert_one(lab_values)
            return 'Lab values submitted successfully!'
        except Exception as e:
            return f'Error inserting lab values: {e}'

    def find_disease_by_lab_values(self, lab_values):
        from datetime import datetime, timedelta

        matching_diseases = []
        for disease in self.rulebase_collection.find():
            disease_matches = True
            matched_rules = []
            for rule in disease['rules']:
                rule_matches = False
                for lab_value in lab_values:
                    try:
                        rule_min_value = float(rule['min_value'])
                        rule_max_value = float(rule['max_value'])
                        lab_value_val = float(lab_value['value'])
                        lab_age = int(lab_value['age'])

                        # Handle age range 'ALL'
                        if rule['age_range'] == 'ALL':
                            age_range_matches = True
                        else:
                            age_range_parts = rule['age_range'].split('-')
                            if len(age_range_parts) == 2:
                                age_range_start, age_range_end = map(int, age_range_parts)
                                age_range_matches = age_range_start <= lab_age <= age_range_end
                            else:
                                age_range_matches = int(age_range_parts[0]) == lab_age

                        # Handle dates and durations
                        try:
                            valid_until_date = datetime.strptime(rule['valid_until'], "%Y-%m-%d")
                            lab_taken_date = datetime.strptime(lab_value['lab_taken_on'], "%Y-%m-%d")
                        except ValueError:
                            valid_until_date = None
                            lab_taken_date = None
                            if 'Days' in rule['valid_until']:
                                days = int(rule['valid_until'].split()[0])
                                valid_until_date = datetime.now() + timedelta(days=days)

                        if (rule['parameter'] == lab_value['parameter'] and
                            rule['unit'] == lab_value['unit'] and
                            rule_min_value <= lab_value_val <= rule_max_value and
                            age_range_matches and
                            (rule['gender'] == lab_value['gender'] or rule['gender'] == 'ALL') and
                            (valid_until_date is None or lab_taken_date is None or lab_taken_date <= valid_until_date)):
                            rule_matches = True
                            matched_rules.append(rule)
                            break
                    
                    except ValueError as e:
                        print(f"ValueError: {e} for parameter: {lab_value.get('parameter', 'Unknown')}")
                        rule_matches = False
                        break
                    
                if not rule_matches:
                    disease_matches = False
                    break

            if disease_matches:
                matching_diseases.append({
                    'disease_code': disease['disease_code'],
                    'matched_rules': matched_rules
                })

        return matching_diseases

    def add_parameter(self, parameter):
        if self.parameters_collection.find_one({'parameter': parameter}):
            return 'Parameter already exists!'
        
        try:
            self.parameters_collection.insert_one({'parameter': parameter})
            return 'Parameter added successfully!'
        except Exception as e:
            return f'Error inserting parameter: {e}'

    def update_parameter(self, old_parameter, new_parameter):
        if not self.parameters_collection.find_one({'parameter': old_parameter}):
            return 'Parameter to update does not exist!'
        
        try:
            self.parameters_collection.update_one({'parameter': old_parameter}, {'$set': {'parameter': new_parameter}})
            return 'Parameter updated successfully!'
        except Exception as e:
            return f'Error updating parameter: {e}'

    def remove_parameter(self, parameter):
        if not self.parameters_collection.find_one({'parameter': parameter}):
            return 'Parameter to remove does not exist!'
        
        try:
            self.parameters_collection.delete_one({'parameter': parameter})
            return 'Parameter removed successfully!'
        except Exception as e:
            return f'Error removing parameter: {e}'

    def get_all_parameters(self):
        # Fetch unique parameters from the parameters_list collection
        parameters = self.parameters_collection.distinct('parameter')
        return parameters

app = Flask(__name__)
app.secret_key = 'random_curemd_secret_key'  # Required for session management

# MongoDB connection
db = Database('mongodb://localhost:27017', 'rulebase', 'RuleBase', 'User_Input_Lab_Values', 'parameters_list')



@app.route('/')
def index():
    if 'user' in session:
        # Fetch parameters from the database
        parameters = db.get_all_parameters()
        return render_template('index.html', parameters=parameters)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # Add your authentication logic here
        if email == ("muntazir.mehdi@curemd.com")and password == ("project1"):  # Use environment variables
            session['user'] = email
            return redirect(url_for('index'))
        else:
            return 'Invalid credentials'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/submit', methods=['POST'])
def submit():
    parameters = request.form.getlist('parameter')
    min_values = request.form.getlist('min_value')
    max_values = request.form.getlist('max_value')
    units = request.form.getlist('unit')
    age_ranges = request.form.getlist('age_range')
    genders = request.form.getlist('gender')
    valid_until_numbers = request.form.getlist('valid_until_number')
    valid_until_units = request.form.getlist('valid_until_unit')
    first_conditions = request.form.getlist('first_condition')

    # Ensure all lists have the same length
    list_lengths = [len(parameters), len(min_values), len(max_values), len(units), len(age_ranges), len(genders), len(valid_until_numbers), len(valid_until_units)]
    if len(set(list_lengths)) != 1:
        return 'Error: Mismatched input lengths!'

    rules = []
    for i in range(len(parameters)):
        valid_until = f"{valid_until_numbers[i]} {valid_until_units[i]}"
        rule = Rule(parameters[i], min_values[i], max_values[i], units[i], age_ranges[i], genders[i], valid_until, first_conditions[i] if i < len(first_conditions) else None)
        rules.append(rule)

    disease_codes = request.form.getlist('disease_code')  # Changed to handle multiple disease codes
    disease_name = request.form['disease_name']
    disease = Disease(disease_codes, disease_name, rules)  # Pass the list of disease codes

    result = db.insert_disease(disease)
    return result

@app.route('/lab_values')
def lab_values():
    return render_template('lab_values.html')

@app.route('/submit_lab_values', methods=['POST'])
def submit_lab_values():
    try:
        parameters = request.form.getlist('parameter')
        values = request.form.getlist('value')
        units = request.form.getlist('unit')
        ages = request.form.getlist('age')
        genders = request.form.getlist('gender')
        lab_taken_on_numbers = request.form.getlist('lab_taken_on_number')
        lab_taken_on_units = request.form.getlist('lab_taken_on_unit')

        lab_values = []
        for i in range(len(parameters)):
            try:
                lab_taken_on = f"{lab_taken_on_numbers[i]} {lab_taken_on_units[i]}"
                lab_values.append({
                    'parameter': parameters[i],
                    'value': float(values[i]),  # Only a single value is provided
                    'unit': units[i],
                    'age': int(ages[i]),
                    'gender': genders[i],
                    'lab_taken_on': lab_taken_on
                })
            except ValueError as e:
                return jsonify({'error': f'Invalid input: {e}'}), 400
            
        # Store lab values in the User_Input_Lab_Values collection
        result = db.insert_lab_values({'lab_values': lab_values})
        if isinstance(result, str):  # Return result if it's a string (success or error message)
            return result

        matching_diseases = db.find_disease_by_lab_values(lab_values)

        matching_codes = [disease['disease_code'] for disease in matching_diseases]
        return jsonify({'matching_codes': matching_codes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin_parameters', methods=['GET', 'POST'])
def admin_parameters():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        action = request.form.get('action')
        parameter = request.form.get('parameter')
        old_parameter = request.form.get('old_parameter')

        if action == 'add':
            result = db.add_parameter(parameter)
        elif action == 'update':
            result = db.update_parameter(old_parameter, parameter)
        elif action == 'remove':
            result = db.remove_parameter(parameter)
        else:
            result = 'Invalid action'

        return redirect(url_for('admin_parameters'))

    parameters = db.get_all_parameters()
    return render_template('admin_parameters.html', parameters=parameters)

if __name__ == '__main__':
    app.run(debug=True)
