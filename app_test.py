from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from pymongo import MongoClient

class Rule:
    def __init__(self, parameter, operator, min_value, max_value, unit, age_range, gender, valid_until, first_condition=None):
        self.parameter = parameter
        self.operator = operator
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
            'operator': self.operator,
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
        self.parameters_collection = self.db[parameters_collection_name]

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

                        if rule['age_range'] == 'ALL':
                            age_range_matches = True
                        else:
                            age_range_parts = rule['age_range'].split('-')
                            if len(age_range_parts) == 2:
                                age_range_start, age_range_end = map(int, age_range_parts)
                                age_range_matches = age_range_start <= lab_age <= age_range_end
                            else:
                                age_range_matches = int(age_range_parts[0]) == lab_age

                        try:
                            valid_until_date = datetime.strptime(rule['valid_until'], "%Y-%m-%d")
                            lab_taken_date = datetime.strptime(lab_value['lab_taken_on'], "%Y-%m-%d")
                        except ValueError:
                            valid_until_date = None
                            lab_taken_date = None
                            if 'Days' in rule['valid_until']:
                                days = int(rule['valid_until'].split()[0])
                                valid_until_date = datetime.now() + timedelta(days=days)

                        # Evaluate based on the operator
                        if rule['operator'] == '=':
                            value_matches = lab_value_val == rule_min_value
                        elif rule['operator'] == '>':
                            value_matches = lab_value_val > rule_min_value
                        elif rule['operator'] == '<':
                            value_matches = lab_value_val < rule_min_value
                        elif rule['operator'] == '>=':
                            value_matches = lab_value_val >= rule_min_value
                        elif rule['operator'] == '<=':
                            value_matches = lab_value_val <= rule_min_value
                        else:
                            value_matches = rule_min_value <= lab_value_val <= rule_max_value  # Default to range comparison

                        if (rule['parameter'] == lab_value['parameter'] and
                            rule['unit'] == lab_value['unit'] and
                            value_matches and
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
        parameters = self.parameters_collection.distinct('parameter')
        return parameters

app = Flask(__name__)
app.secret_key = 'random_curemd_secret_key'

db = Database('mongodb://172.16.105.132:27017/', 'rulebase', 'RuleBase', 'User_Input_Lab_Values', 'parameters_list')

@app.route('/')
def index():
    if 'user' in session:
        parameters = db.get_all_parameters()
        return render_template('index.html', parameters=parameters)
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if email == ("muntazir.mehdi@curemd.com") and password == ("project1"):
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
    try:
        parameters = request.form.getlist('parameter')
        value_types = request.form.getlist('value_type')
        operators_single = request.form.getlist('operator_single')
        operators_range = request.form.getlist('operator_range')
        min_values = request.form.getlist('min_value')
        max_values = request.form.getlist('max_value')
        single_values = request.form.getlist('single_value')
        units = request.form.getlist('unit')
        age_ranges = request.form.getlist('age_range')
        genders = request.form.getlist('gender')
        valid_until_numbers = request.form.getlist('valid_until_number')
        valid_until_units = request.form.getlist('valid_until_unit')
        first_conditions = request.form.getlist('first_condition')

        rules = []
        for i in range(len(parameters)):
            value_type = value_types[i]
            valid_until = f"{valid_until_numbers[i]} {valid_until_units[i]}" if valid_until_numbers[i] and valid_until_units[i] else None
            first_condition = first_conditions[i] if i < len(first_conditions) and first_conditions[i] else None

            if value_type == 'single':
                operator = operators_single[i]
                value = single_values[i]
                min_value = max_value = value
            elif value_type == 'range':
                operator = operators_range[i]
                min_value = min_values[i]
                max_value = max_values[i]
            else:
                return 'Error: Invalid value type specified.', 400

            rule = Rule(
                parameter=parameters[i],
                operator=operator,
                min_value=min_value,
                max_value=max_value,
                unit=units[i],
                age_range=age_ranges[i],
                gender=genders[i],
                valid_until=valid_until,
                first_condition=first_condition
            )
            rules.append(rule)

        disease_code = request.form.get('disease_code')
        disease_name = request.form.get('disease_name')

        if not disease_code or not disease_name:
            return 'Error: Disease code and name are required.', 400

        disease = Disease(disease_code, disease_name, rules)
        result = db.insert_disease(disease)
        return result
    except Exception as e:
        print(f"Error in /submit route: {e}")
        return f'Error processing request: {e}', 500


@app.route('/submit_lab_values', methods=['POST'])
def submit_lab_values():
    try:
        parameters = request.form.getlist('parameter')
        values = request.form.getlist('value')
        units = request.form.getlist('unit')
        ages = request.form.getlist('age')
        genders = request.form.getlist('gender')
        lab_taken_on = request.form.get('lab_taken_on')

        lab_values = []
        for i in range(len(parameters)):
            try:
                lab_values.append({
                    'parameter': parameters[i],
                    'value': float(values[i]),
                    'unit': units[i],
                    'age': int(ages[i]),
                    'gender': genders[i],
                    'lab_taken_on': lab_taken_on
                })
            except ValueError as e:
                return jsonify({'error': f'Invalid input: {e}'}), 400
            
        result = db.insert_lab_values({'lab_values': lab_values})
        if isinstance(result, str):
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
