import streamlit as st
import pandas as pd
import random
import time
from geopy.distance import geodesic

# ------------------------------------------------------------------------------
#                      1) LOAD & CACHE HDB DATA (UNCHANGED)
# ------------------------------------------------------------------------------
@st.cache_data
def load_hdb_data():
    file_path = '/Users/joey.chua/Documents/GitHub/scheduling/HDBPropertyInformation_geocoded.csv'
    hdb_data = pd.read_csv(file_path)
    return hdb_data

hdb_data = load_hdb_data()


# ------------------------------------------------------------------------------
#                      2) NAME AND ADDRESS GENERATION (UNCHANGED)
# ------------------------------------------------------------------------------
def generate_singapore_name():
    first_names = ["Aaliyah", "Aarav", "Chloe", "Ethan", "Isabella", "Liam",
                   "Olivia", "Noah", "Sophia", "Lucas", "Mei Ling", "Jia Hao",
                   "Siti", "Kumar", "Wei Ting"]
    last_names = ["Tan", "Lim", "Lee", "Ng", "Wong", "Chen", "Goh", "Raj", "Kumar",
                  "Singh", "Abdullah", "Ali", "Hassan", "Ong", "Teo"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_singapore_address():
    # Randomly select a block and street from the HDB data
    selected_row = hdb_data.sample(n=1).iloc[0]
    return {
        "address": f"Blk {selected_row['blk_no']} {selected_row['street']}, Singapore",
        "latitude": selected_row['latitude'],
        "longitude": selected_row['longitude']
    }


# ------------------------------------------------------------------------------
#                      3) DISTANCE & SUGGEST DOCTORS (num_suggestions=10)
# ------------------------------------------------------------------------------
def calculate_distances(lat1, lon1, destinations):
    distances = []
    for dest in destinations:
        lat2 = dest['latitude']
        lon2 = dest['longitude']
        distance = geodesic((lat1, lon1), (lat2, lon2)).kilometers
        distances.append((distance, dest))
    return sorted(distances, key=lambda x: x[0])

def get_closest_doctors(patient, doctors, num_suggestions=10):
    lat1 = patient['latitude']
    lon1 = patient['longitude']

    for doctor in doctors:
        if doctor['name'] in st.session_state['scheduled_appointments']:
            last_appointment = st.session_state['scheduled_appointments'][doctor['name']][-1]
            doctor['latitude'] = last_appointment['latitude']
            doctor['longitude'] = last_appointment['longitude']

    distances = calculate_distances(lat1, lon1, doctors)
    if not distances:
        st.error("No valid distances calculated. Check the addresses.")
        return []

    suggestions = []
    for dist, doc in distances[:num_suggestions]:
        label_str = (
            f"{doc['name']} ({doc['specialization']}) - {round(dist, 2)} km\n"
            f"{doc['address']}"
        )
        suggestions.append({
            "label": label_str,
            "name": doc["name"],
            "specialization": doc["specialization"],
            "address": doc["address"],
            "latitude": doc["latitude"],
            "longitude": doc["longitude"],
            "distance": round(dist, 2),
        })
    return suggestions


# ------------------------------------------------------------------------------
#                      4) GENERATE PATIENT/DOCTOR DATA (UNCHANGED)
# ------------------------------------------------------------------------------
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


# ------------------------------------------------------------------------------
#               5) TIME SLOTS & APPOINTMENT OVERLAP LOGIC (UNCHANGED)
# ------------------------------------------------------------------------------
TIME_SLOTS = pd.date_range("09:00", "18:00", freq="30min").strftime("%I:%M %p").tolist()
SLOT_LABEL_TO_INDEX = {label: idx for idx, label in enumerate(TIME_SLOTS)}

def get_slot_indices(slot_list):
    return {SLOT_LABEL_TO_INDEX[s] for s in slot_list}

def is_overlap_allowed(existing_slots, new_slots):
    shared = existing_slots.intersection(new_slots)
    if len(shared) == 0:
        return True
    elif len(shared) > 1:
        return False
    else:
        shared_idx = shared.pop()
        nm, xnm = min(new_slots), max(new_slots)
        em, xem = min(existing_slots), max(existing_slots)
        if xem == nm == shared_idx:  # existing ends where new begins
            return True
        if xnm == em == shared_idx:  # new ends where existing begins
            return True
        return False

def can_assign_appointment(doctor_schedule, new_indices):
    for appt in doctor_schedule:
        existing_set = get_slot_indices(appt["time_slots"])
        if not is_overlap_allowed(existing_set, set(new_indices)):
            return False
    return True

def assign_appointment_to_slot(selected_doctor, appointment):
    doctor_name = selected_doctor["name"]
    if doctor_name not in st.session_state['scheduled_appointments']:
        st.session_state['scheduled_appointments'][doctor_name] = []

    doctor_schedule = st.session_state['scheduled_appointments'][doctor_name]

    preferred_slot = appointment.get("preferred_time_slot")
    if not preferred_slot:
        st.error("No preferred slot found for this patient.")
        return

    if preferred_slot not in SLOT_LABEL_TO_INDEX:
        st.error(f"Preferred slot ({preferred_slot}) is invalid or out of range.")
        return

    start_idx = SLOT_LABEL_TO_INDEX[preferred_slot]
    if start_idx + 2 >= len(TIME_SLOTS):
        st.error(f"Preferred slot of {preferred_slot} cannot fit 1.5 hours before 6:00 PM.")
        return

    new_indices = [start_idx, start_idx+1, start_idx+2]

    if can_assign_appointment(doctor_schedule, new_indices):
        assigned_labels = [TIME_SLOTS[i] for i in new_indices]
        appointment['time_slots'] = assigned_labels
        doctor_schedule.append(appointment)
    else:
        st.error(
            f"No available 1.5-hour block (with 30-min boundary overlap) "
            f"for {appointment['patient_name']} at {preferred_slot}."
        )


# ------------------------------------------------------------------------------
#                6) TABLE DISPLAY (APPENDS PATIENT NAMES IF OVERLAP)
# ------------------------------------------------------------------------------
def display_scheduled_appointments(scheduled_appointments):
    time_slots = pd.date_range("09:00", "18:00", freq="30min").strftime("%I:%M %p").tolist()
    schedule_df = pd.DataFrame(columns=["Doctor"] + time_slots)

    for doctor in st.session_state['doctors']:
        doctor_row = {"Doctor": doctor['name']}
        if doctor['name'] in scheduled_appointments:
            for appointment in scheduled_appointments[doctor['name']]:
                for slot in appointment['time_slots']:
                    if slot not in doctor_row or doctor_row[slot] == "-":
                        doctor_row[slot] = appointment['patient_name']
                    else:
                        # There's already a name; append new name to show overlap
                        doctor_row[slot] += " / " + appointment['patient_name']
        schedule_df = pd.concat([schedule_df, pd.DataFrame([doctor_row])], ignore_index=True)

    schedule_df.fillna("-", inplace=True)

    def style_cell(value):
        if value != "-":
            return f"<td style='background-color: #d4edda; color: #155724; text-align: center;'>{value}</td>"
        else:
            return f"<td style='background-color: #f8d7da; color: #721c24; text-align: center;'>-</td>"

    table_html = "<table style='width:100%; border-collapse: collapse;'>"
    table_html += "<thead><tr>"
    for col in schedule_df.columns:
        table_html += f"<th style='border: 1px solid black; padding: 5px;'>{col}</th>"
    table_html += "</tr></thead><tbody>"

    for _, row in schedule_df.iterrows():
        table_html += "<tr>"
        for col in schedule_df.columns:
            table_html += style_cell(row[col])
        table_html += "</tr>"
    table_html += "</tbody></table>"

    st.markdown(table_html, unsafe_allow_html=True)


# ------------------------------------------------------------------------------
#                   7) MAIN APP FLOW
#                      (SORT BY TIME + EXPANDED DETAILS)
# ------------------------------------------------------------------------------
if 'patients' not in st.session_state:
    st.session_state['patients'] = generate_patient_data(30)
if 'doctors' not in st.session_state:
    st.session_state['doctors'] = generate_doctor_data(10)
if 'scheduled_appointments' not in st.session_state:
    st.session_state['scheduled_appointments'] = {}
if 'selected_patient_index' not in st.session_state:
    st.session_state['selected_patient_index'] = None

# ---------------- SORT PATIENTS BY PREFERRED TIME SLOT (ASC) ------------------
# We'll rely on SLOT_LABEL_TO_INDEX to get a numeric index for each slot
st.session_state['patients'].sort(key=lambda p: SLOT_LABEL_TO_INDEX[p["preferred_time_slot"]])

# Now create a DataFrame for easy referencing in the selectbox
patients_df = pd.DataFrame(st.session_state['patients'])
doctors_df = pd.DataFrame(st.session_state['doctors'])

st.header("Unscheduled Appointments")

selected_patient = None
if st.session_state['selected_patient_index'] is not None:
    # This means user has previously selected a patient
    selected_patient = st.session_state['patients'][st.session_state['selected_patient_index']]

if not patients_df.empty:
    # Because we sorted 'patients' above, the order in the selectbox is ascending by time
    patient_index = st.selectbox(
        "Select an unscheduled appointment to view details and assign:",
        range(len(patients_df)),
        format_func=lambda i: (
            f"{patients_df['name'][i]} ({patients_df['appointment_type'][i]})"
        ),
        index=st.session_state['selected_patient_index']
              if st.session_state['selected_patient_index'] is not None
              else 0
    )

    # Update the session state
    st.session_state['selected_patient_index'] = patient_index
    selected_patient = st.session_state['patients'][patient_index]

    # By default expanded=True
    with st.expander(f"Details for {selected_patient['name']}", expanded=True):
        st.write(f"**Address:** {selected_patient['address']}")
        st.write(f"**Appointment Type:** {selected_patient['appointment_type']}")
        st.write(f"**Preferred Time Slot:** {selected_patient['preferred_time_slot']}")

        # Now retrieving 10 suggestions
        suggested_doctors = get_closest_doctors(selected_patient, st.session_state['doctors'], num_suggestions=10)

        st.subheader("Suggested Doctors")
        if suggested_doctors:
            assigned_doctor = st.selectbox("Select doctor to assign:", options=suggested_doctors, format_func=lambda x: x["label"])
            if st.button("Assign Appointment"):
                if assigned_doctor:
                    new_appointment = {
                        'patient_name': selected_patient['name'],
                        'appointment_type': selected_patient['appointment_type'],
                        'latitude': selected_patient['latitude'],
                        'longitude': selected_patient['longitude'],
                        'preferred_time_slot': selected_patient['preferred_time_slot'],
                    }
                    assign_appointment_to_slot(assigned_doctor, new_appointment)

                    # If successfully assigned => 'time_slots' in new_appointment
                    if 'time_slots' in new_appointment:
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
