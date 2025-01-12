import streamlit as st
import pandas as pd
import random
import time
from geopy.distance import geodesic

# Load geocoded HDB property data
@st.cache_data
def load_hdb_data():
    file_path = '/Users/joey.chua/Documents/GitHub/scheduling/HDBPropertyInformation_geocoded.csv'
    hdb_data = pd.read_csv(file_path)
    return hdb_data

hdb_data = load_hdb_data()

def generate_singapore_name():
    first_names = ["Aaliyah", "Aarav", "Chloe", "Ethan", "Isabella", "Liam", "Olivia", "Noah", "Sophia", "Lucas", "Mei Ling", "Jia Hao", "Siti", "Kumar", "Wei Ting"]
    last_names = ["Tan", "Lim", "Lee", "Ng", "Wong", "Chen", "Goh", "Raj", "Kumar", "Singh", "Abdullah", "Ali", "Hassan", "Ong", "Teo"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_singapore_address():
    # Randomly select a block and street from the HDB data
    selected_row = hdb_data.sample(n=1).iloc[0]
    return {
        "address": f"Blk {selected_row['blk_no']} {selected_row['street']}, Singapore",
        "latitude": selected_row['latitude'],
        "longitude": selected_row['longitude']
    }

def calculate_distances(lat1, lon1, destinations):
    distances = []
    for dest in destinations:
        lat2 = dest['latitude']
        lon2 = dest['longitude']
        distance = geodesic((lat1, lon1), (lat2, lon2)).kilometers
        distances.append((distance, dest))
    return sorted(distances, key=lambda x: x[0])

def get_closest_doctors(patient, doctors, num_suggestions=5):
    lat1 = patient['latitude']
    lon1 = patient['longitude']

    # Calculate distances considering existing appointments or starting point
    for doctor in doctors:
        if doctor['name'] in st.session_state['scheduled_appointments']:
            last_appointment = st.session_state['scheduled_appointments'][doctor['name']][-1]
            doctor['latitude'] = last_appointment['latitude']
            doctor['longitude'] = last_appointment['longitude']

    distances = calculate_distances(lat1, lon1, doctors)
    if not distances:
        st.error("No valid distances calculated. Check the addresses.")
        return []
    return [f"{doc['name']} ({doc['specialization']}) - {round(dist, 2)} km" for dist, doc in distances[:num_suggestions]]

def generate_patient_data(num_patients):
    patients = []
    appointment_types = ['Consultation', 'Baby Vaccines']
    preferred_time_slots = pd.date_range("09:00", "18:00", freq="30min").strftime("%I:%M %p").tolist()
    for _ in range(num_patients):
        address_info = generate_singapore_address()
        patients.append({
            'name': generate_singapore_name(),
            'address': address_info['address'],
            'latitude': address_info['latitude'],
            'longitude': address_info['longitude'],
            'appointment_type': random.choice(appointment_types),
            'preferred_time_slot': random.choice(preferred_time_slots),
        })
    return patients

def generate_doctor_data(num_doctors):
    doctors = []
    specializations = ['General Medicine', 'Pediatrics']
    for _ in range(num_doctors):
        address_info = generate_singapore_address()
        doctors.append({
            'name': generate_singapore_name(),
            'specialization': random.choice(specializations),
            'address': address_info['address'],
            'latitude': address_info['latitude'],
            'longitude': address_info['longitude'],
        })
    return doctors

def assign_appointment_to_slot(doctor_name, appointment):
    time_slots = pd.date_range("09:00", "18:00", freq="30min").strftime("%I:%M %p").tolist()
    if doctor_name not in st.session_state['scheduled_appointments']:
        st.session_state['scheduled_appointments'][doctor_name] = []

    # Get the current schedule for the doctor
    doctor_schedule = st.session_state['scheduled_appointments'][doctor_name]

    # Find the nearest available slot with 30 minutes overlap
    for idx, slot in enumerate(time_slots):
        if all(
            slot not in app['time_slots']
            for app in doctor_schedule
        ):
            end_idx = idx + 3  # 1.5-hour slot = 3 intervals
            appointment['time_slots'] = time_slots[idx:end_idx]
            doctor_schedule.append(appointment)
            return

    st.error("No available slots for this doctor.")

if 'patients' not in st.session_state:
    st.session_state['patients'] = generate_patient_data(30)
if 'doctors' not in st.session_state:
    st.session_state['doctors'] = generate_doctor_data(10)
if 'scheduled_appointments' not in st.session_state:
    st.session_state['scheduled_appointments'] = {}
if 'selected_patient_index' not in st.session_state:
    st.session_state['selected_patient_index'] = None

patients_df = pd.DataFrame(st.session_state['patients'])
doctors_df = pd.DataFrame(st.session_state['doctors'])

def display_scheduled_appointments(scheduled_appointments):
    # Create a schedule with 30-minute intervals from 9 AM to 6 PM
    time_slots = pd.date_range("09:00", "18:00", freq="30min").strftime("%I:%M %p").tolist()

    # Initialize a DataFrame for the schedule
    schedule_df = pd.DataFrame(columns=["Doctor"] + time_slots)

    for doctor in st.session_state['doctors']:
        doctor_row = {"Doctor": doctor['name']}
        if doctor['name'] in scheduled_appointments:
            for appointment in scheduled_appointments[doctor['name']]:
                for slot in appointment['time_slots']:
                    doctor_row[slot] = appointment['patient_name']
        schedule_df = pd.concat([schedule_df, pd.DataFrame([doctor_row])], ignore_index=True)

    # Fill missing values with "-" to ensure the table is displayed
    schedule_df.fillna("-", inplace=True)
    st.dataframe(schedule_df)

st.header("Unscheduled Appointments")

selected_patient = None
if st.session_state['selected_patient_index'] is not None:
    selected_patient = st.session_state['patients'][st.session_state['selected_patient_index']]

if not patients_df.empty:
    patient_index = st.selectbox(
        "Select an unscheduled appointment to view details and assign:",
        range(len(patients_df)),
        format_func=lambda i: f"{patients_df['name'][i]} ({patients_df['appointment_type'][i]})",
        index=st.session_state['selected_patient_index'] if st.session_state['selected_patient_index'] is not None else 0
    )

    st.session_state['selected_patient_index'] = patient_index
    selected_patient = st.session_state['patients'][patient_index]

    with st.expander(f"Details for {selected_patient['name']}"):
        st.write(f"**Address:** {selected_patient['address']}")
        st.write(f"**Appointment Type:** {selected_patient['appointment_type']}")
        st.write(f"**Preferred Time Slot:** {selected_patient['preferred_time_slot']}")

        suggested_doctors = get_closest_doctors(selected_patient, st.session_state['doctors'])

        st.subheader("Suggested Doctors")
        if suggested_doctors:
            assigned_doctor = st.selectbox("Select doctor to assign:", options=suggested_doctors)
            if st.button("Assign Appointment"):
                if assigned_doctor:
                    new_appointment = {
                        'patient_name': selected_patient['name'],
                        'appointment_type': selected_patient['appointment_type'],
                        'latitude': selected_patient['latitude'],
                        'longitude': selected_patient['longitude']
                    }
                    assign_appointment_to_slot(assigned_doctor, new_appointment)
                    st.session_state['patients'].pop(st.session_state['selected_patient_index'])
                    st.session_state['selected_patient_index'] = None
                    st.success("Appointment assigned!")
                    st.experimental_rerun()
                else:
                    st.error("Please select a doctor.")
        else:
            st.write("No doctors found, please try again.")
else:
    st.write("No unscheduled appointments.")

st.header("Existing Appointments")
display_scheduled_appointments(st.session_state['scheduled_appointments'])
