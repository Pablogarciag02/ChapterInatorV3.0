import streamlit as st
import requests
import json
import time
from concurrent.futures import ThreadPoolExecutor
import os
import hashlib

#Adding the llama parse dependency requirements.
from llama_parse import LlamaParse
import nest_asyncio
nest_asyncio.apply()  # Needed for Streamlit compatibility

LLAMAPARSE_API_KEY = st.secrets["LLAMAPARSE_API_KEY"]
#Test to see if its uploaded

def check_password():
    """Returns True if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if hashlib.sha256(st.session_state["password"].encode()).hexdigest() == st.secrets["password_hash"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    st.text_input("Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state:
        st.error("Password incorrect")
    return False

# --- CONFIGURATION & CONSTANTS ---

# Set Streamlit page configuration
st.set_page_config(
    page_title="Ebook Generation Pipeline",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Authentication and Endpoints from documentation
API_KEY = st.secrets["API_KEY"]
API_BASE_URL = "https://app.wordware.ai/api/released-app"

APP_IDS = {
    "compendio_to_markdown": "ac114c48-be3a-4ab5-98ee-02a7d11c8dd7",
    "compendio_to_markdown2": "a26d2240-33cf-456a-8e6b-974cdef320ee",
    "project_brief_to_markdown": "b198e35c-9089-4dc4-a281-92bbb04d7528",
    "mapping_referencias": "da1c1988-c58f-4574-be2c-822cd743179c",
    "mapping_citas": "d5202c5b-316c-466e-a85a-3d2e3d7fe405",
    # "mapping_tablas": "3311cdd6-39ed-47bc-9173-c2de11afe82a",
    "mapping_tablas": "fc31e5c0-a986-4df1-b761-8a48c7d6824e",
    "mapping_logic": "c36eb029-1b08-4337-af35-4df4be3bef38",
    "theme_selector": "a9ba5428-5286-46f3-b3ca-1ba824c686d9",
    "chapter_creator": "75ad4354-dd42-406e-be67-67073b3b82a2",
    "arcoNarrativo": "8582b48d-1343-4f0f-80df-271662fa0ce2",
    # NOTE: Placeholder as per documentation. Update if a real ID is provided.
    "table_generator": "660116bf-1f90-496b-aa12-d357044867ef" 
}

# --- SESSION STATE MANAGEMENT ---

def initialize_session_state():
    """Initializes all required session state variables with default values."""
    defaults = {
        # General app state
        'current_stage': 1,
        
        # Stage Status Tracking
        'stage_1_status': 'pending', 'stage_2_status': 'pending', 'stage_3_status': 'pending',
        'stage_4_status': 'pending', 'stage_5_status': 'pending',
        'stage_2_1_status': 'pending', 'stage_2_2_status': 'pending',
        'stage_2_3_status': 'pending', 'stage_2_4_status': 'pending',

        # Primary Data Storage
        'compendio_md': "", 'project_brief_md': "", 'mapping_combined': "",
        'skeleton': {}, 'generated_chapters': {}, 'final_ebook': "",

        # User settings for Stage 3
        'topic_input': "", 'reference_count': 25, 'page_count': "40-50", 'subtemas_enabled': False,

        # File management
        'uploaded_files': {},

        # Intermediate outputs for modular recovery
        'stage_1_1_output': "", 'stage_1_2_output': "",
        'mapping_referencias': "", 'mapping_citas': "", 'mapping_tablas': "",

        # Sequential Chapter Generation Management
        'chapter_sequence': [], 'current_chapter_index': 0, 'previous_context': "",
        'chapters_completed': [], 'book_complete': False
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def clear_all_session_data():
    """Resets the entire pipeline by clearing relevant session state keys."""
    keys_to_clear = [key for key in st.session_state.keys() if key.startswith((
        'stage_', 'compendio_', 'project_', 'mapping_', 'skeleton', 'generated_', 
        'final_', 'topic_', 'reference_', 'page_', 'subtemas_', 'uploaded_', 
        'chapter_', 'current_', 'previous_', 'book_'))]
    
    for key in keys_to_clear:
        del st.session_state[key]
    
    st.success("All pipeline data has been cleared. Please refresh the page to start over.")
    time.sleep(2)
    st.rerun()

# --- FILE UPLOAD HELPERS ---

def upload_to_0x0(file):
    """Uploads a file to 0x0.st."""
    try:
        file.seek(0)
        files = {"file": (file.name, file, file.type)}
        response = requests.post("https://0x0.st", files=files, timeout=60)
        if response.status_code == 200 and response.text.strip().startswith("https://"):
            return response.text.strip()
    except Exception as e:
        st.toast(f"Error with 0x0.st: {e}", icon="🔥")
    return None

def upload_to_catbox(file):
    """Uploads a file to catbox.moe."""
    try:
        file.seek(0)
        files = {"fileToUpload": (file.name, file, file.type)}
        data = {"reqtype": "fileupload"}
        response = requests.post("https://catbox.moe/user/api.php", files=files, data=data, timeout=60)
        if response.status_code == 200 and response.text.strip().startswith("https://"):
            return response.text.strip()
    except Exception as e:
        st.toast(f"Error with catbox.moe: {e}", icon="🔥")
    return None

def upload_to_tmpfiles(file):
    """Uploads a file to tmpfiles.org."""
    try:
        file.seek(0)
        files = {"file": (file.name, file, file.type)}
        response = requests.post("https://tmpfiles.org/api/v1/upload", files=files, timeout=60)
        if response.status_code == 200:
            data = response.json()
            url = data.get("data", {}).get("url", "")
            if url:
                return url.replace("https://tmpfiles.org/", "https://tmpfiles.org/dl/")
    except Exception as e:
        st.toast(f"Error with tmpfiles.org: {e}", icon="🔥")
    return None

def upload_to_fileio(file):
    """Uploads a file to file.io."""
    try:
        file.seek(0)
        files = {"file": (file.name, file, file.type)}
        response = requests.post("https://file.io", files=files, timeout=60)
        if response.status_code == 200:
            data = response.json()
            return data.get("link", "")
    except Exception as e:
        st.toast(f"Error with file.io: {e}", icon="🔥")
    return None

def upload_file_with_fallback(file):
    """Tries multiple upload services until one succeeds."""
    services = [upload_to_0x0, upload_to_catbox, upload_to_tmpfiles, upload_to_fileio]
    for service in services:
        service_name = service.__name__.replace('upload_to_', '').replace('_', ' ').title()
        with st.spinner(f"Uploading via {service_name}..."):
            url = service(file)
            if url:
                st.toast(f"Successfully uploaded via {service_name}!", icon="✅")
                return url
    st.error("All file upload services failed. Please check your network or try again later.")
    return None



# --- API CALLER & STREAMING ---

def process_wordware_api(app_id, inputs, stream_container=None):
    """
    Calls a Wordware API endpoint, handles streaming responses, and returns the final output.
    If a stream_container is provided, it writes chunks to it in real-time.
    """
    url = f"{API_BASE_URL}/{app_id}/run"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"inputs": inputs}
    
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=1600) #increased timeout time because of 2.3 mapping.
        response.raise_for_status()

        final_output = None
        full_response_text = ""
        
        # Use a generator function for streaming to st.write_stream
        def stream_generator():
            nonlocal final_output
            for line in response.iter_lines():
                if line:
                    try:
                        content = json.loads(line.decode('utf-8'))
                        value = content.get('value', {})
                        
                        if value.get('type') == 'chunk':
                            yield value.get('value', '')
                        elif value.get('type') == 'outputs':
                            final_output = value
                    except json.JSONDecodeError:
                        st.warning(f"Could not decode JSON line: {line}")
        
        if stream_container:
            stream_container.write_stream(stream_generator)
        else:
            # If not streaming to UI, just consume the generator to get the final output
            for _ in stream_generator():
                pass
        if final_output:
            # Assuming the main output is in a key named 'output', 'text', or the first value
            output_data = final_output.get('values', {})
            if 'output' in output_data:
                return output_data['output']
            elif 'text' in output_data:
                return output_data['text']
            # Fallback for varied output structures
            elif output_data:
                # first_key = next(iter(output_data))
                # return output_data[first_key]
                return output_data
        return None

    except requests.exceptions.RequestException as e:
        st.error(f"API Request Failed: {e}")
        try:
            st.error(f"Error details: {response.json()}")
        except:
            st.error(f"Error details: {response.text}")
        return None

# --- UI RENDERING FUNCTIONS ---

def render_status_icon(status):
    """Returns a status icon based on the stage status."""
    if status == 'completed':
        return "✅"
    elif status == 'in_progress':
        return "🔄"
    elif status == 'error':
        return "❌"
    return "⚪"

def render_progress_indicator():
    """Displays the main pipeline progress bar at the top."""
    st.subheader("Ebook Generation Progress")
    cols = st.columns(5)
    stages = [
        ("1. Content", st.session_state.stage_1_status),
        ("2. Mapping", st.session_state.stage_2_status),
        ("3. Structure", st.session_state.stage_3_status),
        ("4. Chapters", st.session_state.stage_4_status),
        ("5. Assembly", st.session_state.stage_5_status)
    ]
    for col, (name, status) in zip(cols, stages):
        with col:
            icon = render_status_icon(status)
            st.markdown(f"**{name}** {icon}")
    st.divider()


def render_sidebar():
    """Renders the navigation sidebar with stage locking."""
    with st.sidebar:
        st.title("📚 Pipeline Stages")
        st.markdown("Navigate through the ebook generation process.")

        # Check if any chapters have been generated - if so, lock previous stages
        has_generated_chapters = len(st.session_state.generated_chapters) > 0
        is_generating = st.session_state.get('generation_in_progress', False)
        
        # Check if all chapters are complete for Stage 5 access
        all_chapters_complete = False
        if st.session_state.chapter_sequence:
            completed = len([c for c in st.session_state.chapter_sequence if c in st.session_state.generated_chapters])
            total = len(st.session_state.chapter_sequence)
            all_chapters_complete = (completed >= total and total > 0)
        
        if has_generated_chapters:
            st.warning("🔒 Etapas 1-3 bloqueadas. Ya iniciaste la generación de capítulos.")

        # Stage 1
        st.button(
            "Stage 1: Content Processing", 
            on_click=lambda: st.session_state.update(current_stage=1), 
            use_container_width=True, 
            type="primary" if st.session_state.current_stage == 1 else "secondary",
            disabled=has_generated_chapters or is_generating
        )
        
        # Stage 2
        st.button(
            "Stage 2:  Reference & Citation Mapping", 
            on_click=lambda: st.session_state.update(current_stage=2), 
            use_container_width=True, 
            disabled=st.session_state.stage_1_status != 'completed' or has_generated_chapters or is_generating, 
            type="primary" if st.session_state.current_stage == 2 else "secondary"
        )
        
        # Stage 3
        st.button(
            "Stage 3: Structure Creation", 
            on_click=lambda: st.session_state.update(current_stage=3), 
            use_container_width=True, 
            disabled=st.session_state.stage_2_status != 'completed' or has_generated_chapters or is_generating, 
            type="primary" if st.session_state.current_stage == 3 else "secondary"
        )
        
        # Stage 4
        st.button(
            "Stage 4: Chapter Generation", 
            on_click=lambda: st.session_state.update(current_stage=4), 
            use_container_width=True, 
            disabled=st.session_state.stage_3_status != 'completed' or is_generating, 
            type="primary" if st.session_state.current_stage == 4 else "secondary"
        )
        
        # Stage 5
        st.button(
            "Stage 5: Final Assembly", 
            on_click=lambda: st.session_state.update(current_stage=5), 
            use_container_width=True, 
            disabled=not all_chapters_complete or is_generating, 
            type="primary" if st.session_state.current_stage == 5 else "secondary"
        )
        
        st.divider()
        st.warning("Clearing data will reset the entire process and cannot be undone.")
        if st.button("🔄 Clear All Data & Restart", use_container_width=True, type="primary", disabled=is_generating):
            clear_all_session_data()

## --- Stage 1: Content Processing (UTILIZES WORDWARE AS PARSER) ---
def render_stage_1():
    st.header("Stage 1: Content Processing")
    st.markdown("Upload your source PDF documents. The 'Compendio' is required, while the 'Project Brief' is optional but recommended for better context.")

    compendio_file = st.file_uploader("Upload Compendio PDF (Required)", type="pdf", key="compendio_uploader")
    project_brief_file = st.file_uploader("Upload Project Brief PDF (Optional)", type="pdf", key="project_brief_uploader")

    if st.button("Process Source Documents", disabled=(not compendio_file)):
        st.session_state.stage_1_status = 'in_progress'
        
        compendio_url = upload_file_with_fallback(compendio_file)
        if not compendio_url:
            st.session_state.stage_1_status = 'error'
            st.error("Failed to upload the Compendio PDF. Cannot proceed.")
            return

        st.session_state.uploaded_files['compendio'] = {"url": compendio_url, "name": compendio_file.name}
        
        brief_url = None
        if project_brief_file:
            brief_url = upload_file_with_fallback(project_brief_file)
            if brief_url:
                st.session_state.uploaded_files['project_brief'] = {"url": brief_url, "name": project_brief_file.name}

        # Use ThreadPoolExecutor to run API calls in parallel
        with ThreadPoolExecutor(max_workers=3) as executor:
            st.info("Starting parallel processing of documents... This may take several minutes.")
            
            # Prepare inputs
            compendio_input = {"type": "file", "file_type": "application/pdf", "file_url": compendio_url, "file_name": compendio_file.name}
            
            # Submit jobs
            future1 = executor.submit(process_wordware_api, APP_IDS["compendio_to_markdown"], {"CompendioPDF": compendio_input})
            future2 = executor.submit(process_wordware_api, APP_IDS["compendio_to_markdown2"], {"CompendioPDF": compendio_input})
            future3 = None
            if brief_url:
                brief_input = {"type": "file", "file_type": "application/pdf", "file_url": brief_url, "file_name": project_brief_file.name}
                future3 = executor.submit(process_wordware_api, APP_IDS["project_brief_to_markdown"], {"ProjectBriefPDF": brief_input})
            with st.status("Processing Compendio (Part 1/2)..."):
                result1 = future1.result()
                st.session_state.stage_1_1_output = result1 if isinstance(result1, str) else list(result1.values())[0]
            with st.status("Processing Compendio (Part 2/2)..."):
                result2 = future2.result()
                st.session_state.stage_1_2_output = result2 if isinstance(result2, str) else list(result2.values())[0]

        if st.session_state.stage_1_1_output and st.session_state.stage_1_2_output:
            st.session_state.compendio_md = st.session_state.stage_1_1_output + "\n\n" + st.session_state.stage_1_2_output
            st.session_state.stage_1_status = 'completed'
            st.success("Stage 1 Completed! All documents processed successfully.")
        else:
            st.session_state.stage_1_status = 'error'
            st.error("An error occurred during document processing. Check the logs above.")
            
        st.rerun()

    if st.session_state.stage_1_status == 'completed':
        st.success("✅ Stage 1 is complete. You can now proceed to Stage 2.")
        with st.expander("View Processed Compendio Markdown"):
            st.markdown(st.session_state.compendio_md)
            st.download_button(
                label="Download Compendio.md",
                data=st.session_state.compendio_md.encode('utf-8'),
                file_name="compendio.md",
                mime="text/markdown"
            )
        if st.session_state.project_brief_md:
            with st.expander("View Processed Project Brief Markdown"):
                st.markdown(st.session_state.project_brief_md)
                st.download_button(
                    label="Download Project_Brief.md",
                    data=st.session_state.project_brief_md.encode('utf-8'),
                    file_name="project_brief.md",
                    mime="text/markdown"
                )

# # # ## --- Stage 1: Content Processing with LlamaParse ---
# # # def render_stage_1():
# # #     st.header("Stage 1: Content Processing")
# # #     st.markdown("Upload your source PDF documents. The 'Compendio' is required, while the 'Project Brief' is optional but recommended for better context.")

# # #     compendio_file = st.file_uploader("Upload Compendio PDF (Required)", type="pdf", key="compendio_uploader")
# # #     project_brief_file = st.file_uploader("Upload Project Brief PDF (Optional)", type="pdf", key="project_brief_uploader")

# # #     if st.button("Process Source Documents", disabled=(not compendio_file)):
# # #         st.session_state.stage_1_status = 'in_progress'
        
# # #         # Import LlamaParse here to avoid issues if not used
# # #         try:
# # #             from llama_parse import LlamaParse
# # #             import nest_asyncio
# # #             nest_asyncio.apply()
# # #         except ImportError:
# # #             st.error("LlamaParse not installed. Please run: pip install llama-parse nest-asyncio")
# # #             st.session_state.stage_1_status = 'error'
# # #             return
        
# # #         # Process Compendio
# # #         with st.spinner(f"Processing {compendio_file.name} with LlamaParse..."):
# # #             try:
# # #                 # Initialize parser with Agentic-equivalent settings
# # #                 parser = LlamaParse(
# # #                     api_key=st.secrets["LLAMAPARSE_API_KEY"],
# # #                     result_type="markdown",
# # #                     parsing_instruction="Extract all text content including ALL tables. Preserve complete table structure with proper markdown formatting. Include all citations, references, and footnotes.",
# # #                     verbose=True,
# # #                     invalidate_cache=True
# # #                 )
                
# # #                 # Save file temporarily
# # #                 import tempfile
# # #                 import os
                
# # #                 with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
# # #                     tmp_file.write(compendio_file.getvalue())
# # #                     tmp_file_path = tmp_file.name
                
# # #                 # Parse the file
# # #                 documents = parser.load_data(tmp_file_path)
                
# # #                 # Clean up temp file
# # #                 os.unlink(tmp_file_path)
                
# # #                 # Combine all pages into single markdown
# # #                 compendio_md = "\n\n".join([doc.text for doc in documents])
                
# # #                 if not compendio_md:
# # #                     raise ValueError("No content extracted from Compendio")
                    
# # #                 st.session_state.compendio_md = compendio_md
# # #                 st.success(f"✅ Compendio processed: {len(compendio_md)} characters extracted")
                
# # #             except Exception as e:
# # #                 st.session_state.stage_1_status = 'error'
# # #                 st.error(f"Failed to process Compendio: {str(e)}")
# # #                 return
        
# # #         # Process Project Brief if provided
# # #         st.session_state.project_brief_md = ""
# # #         if project_brief_file:
# # #             with st.spinner(f"Processing {project_brief_file.name} with LlamaParse..."):
# # #                 try:
# # #                     # Use same parser settings
# # #                     parser_brief = LlamaParse(
# # #                         api_key=st.secrets["LLAMAPARSE_API_KEY"],
# # #                         result_type="markdown",
# # #                         parsing_instruction="Extract all text content including tables and references.",
# # #                         verbose=True,
# # #                         invalidate_cache=True
# # #                     )
                    
# # #                     with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
# # #                         tmp_file.write(project_brief_file.getvalue())
# # #                         tmp_file_path = tmp_file.name
                    
# # #                     documents_brief = parser_brief.load_data(tmp_file_path)
# # #                     os.unlink(tmp_file_path)
                    
# # #                     brief_md = "\n\n".join([doc.text for doc in documents_brief])
                    
# # #                     if brief_md:
# # #                         st.session_state.project_brief_md = brief_md
# # #                         st.success(f"✅ Project Brief processed: {len(brief_md)} characters extracted")
# # #                     else:
# # #                         st.warning("Project Brief processed but no content extracted, continuing without it.")
                        
# # #                 except Exception as e:
# # #                     st.warning(f"Could not process Project Brief: {str(e)}. Continuing with Compendio only.")
        
# # #         # Mark stage as complete
# # #         st.session_state.stage_1_status = 'completed'
# # #         st.success("Stage 1 Completed! Documents processed successfully.")
# # #         st.rerun()

# # #     # Display results if stage is completed
# # #     if st.session_state.stage_1_status == 'completed':
# # #         st.success("✅ Stage 1 is complete. You can now proceed to Stage 2.")
        
# # #         # Show Compendio content
# # #         with st.expander("View Processed Compendio Markdown"):
# # #             st.markdown(st.session_state.compendio_md[:2000] + "..." if len(st.session_state.compendio_md) > 2000 else st.session_state.compendio_md)
# # #             st.download_button(
# # #                 label="Download Compendio.md",
# # #                 data=st.session_state.compendio_md.encode('utf-8'),
# # #                 file_name="compendio.md",
# # #                 mime="text/markdown"
# # #             )
        
# # #         # Show Project Brief content if exists
# # #         if st.session_state.project_brief_md:
# # #             with st.expander("View Processed Project Brief Markdown"):
# # #                 st.markdown(st.session_state.project_brief_md[:2000] + "..." if len(st.session_state.project_brief_md) > 2000 else st.session_state.project_brief_md)
# # #                 st.download_button(
# # #                     label="Download Project_Brief.md",
# # #                     data=st.session_state.project_brief_md.encode('utf-8'),
# # #                     file_name="project_brief.md",
# # #                     mime="text/markdown"
# # #                 )

## --- Stage 2: Reference Mapping ---
def render_stage_2():
    st.header("Stage 2: Reference & Citation Mapping")
    st.markdown("This stage automatically extracts and maps all references, citations, and tables from the processed content. Click the button below to begin.")

    if st.button("Start Reference Mapping", disabled=(st.session_state.stage_1_status != 'completed')):
        st.session_state.stage_2_status = 'in_progress'
            # Run 2.1 Mapping_Referencias
        with st.spinner("Step 2.1: Extracting Bibliography References..."):
            inputs_2_1 = {"compendio": st.session_state.compendio_md, "projectBrief": st.session_state.project_brief_md}
            result = process_wordware_api(APP_IDS["mapping_referencias"], inputs_2_1)
            if result:
                # Extract just the mapeoReferencias object, not the whole response
                st.session_state.mapping_referencias = result.get("mapeoReferencias", result)
                st.session_state.stage_2_1_status = 'completed'
                st.toast("Step 2.1: References extracted.", icon="✅")
            else:
                st.session_state.stage_2_status = 'error'
                st.error("Failed at Step 2.1. Cannot proceed.")
                return

        # Run 2.2 Mapping_Citas
        with st.spinner("Step 2.2: Mapping In-Text Citations..."):
            inputs_2_2 = {
                "compendio": st.session_state.compendio_md, 
                "projectBrief": st.session_state.project_brief_md,
                "2.1Mapping_Referencias": json.dumps(st.session_state.mapping_referencias)
            }
            result = process_wordware_api(APP_IDS["mapping_citas"], inputs_2_2)
            if result:
                # Extract just the mapeoCitas object
                st.session_state.mapping_citas = result.get("mapeoCitas", result)
                st.session_state.stage_2_2_status = 'completed'
                st.toast("Step 2.2: Citations mapped.", icon="✅")
            else:
                st.session_state.stage_2_status = 'error'
                st.error("Failed at Step 2.2. Cannot proceed.")
                return

        # Run 2.3 Mapping_Tablas
        with st.spinner("Step 2.3: Mapping Tables and Figures..."):
            inputs_2_3 = {
                "compendio": st.session_state.compendio_md,
                "projectBrief": st.session_state.project_brief_md,
                "2.1Mapping_Referencias": json.dumps(st.session_state.mapping_referencias),
                "2.2Mapping_citas": json.dumps(st.session_state.mapping_citas)  # Fixed capitalization
            }
            result = process_wordware_api(APP_IDS["mapping_tablas"], inputs_2_3)
            if result:
                # Extract just the mapeoTablas object
                st.session_state.mapping_tablas = result.get("mapeoTablas", result)
                st.session_state.stage_2_3_status = 'completed'
                st.toast("Step 2.3: Tables mapped.", icon="✅")
            else:
                st.session_state.stage_2_status = 'error'
                st.error("Failed at Step 2.3. Cannot proceed.")
                return

            # Run 2.4 MappingLogic
            with st.spinner("Step 2.4: Combining All Mappings..."):
                inputs_2_4 = {
                    "mapeoCitas": json.dumps(st.session_state.mapping_citas),
                    "mapeoReferencias": json.dumps(st.session_state.mapping_referencias),
                    "mapeoTablas": json.dumps(st.session_state.mapping_tablas)
                }
                result = process_wordware_api(APP_IDS["mapping_logic"], inputs_2_4)
                if result:
                    st.session_state.mapping_combined = result
                    st.session_state.stage_2_4_status = 'completed'
                    st.session_state.stage_2_status = 'completed'
                    st.success("Stage 2 Completed! All references, citations, and tables have been mapped.")
                else:
                    st.session_state.stage_2_status = 'error'
                    st.error("Failed at Step 2.4. Could not combine mappings.")
            st.rerun()

    if st.session_state.stage_2_status == 'completed':
        st.success("✅ Stage 2 is complete. You can now proceed to Stage 3.")
        with st.expander("View Combined Mapping Data (JSON)"):
            # st.json(st.session_state.mapping_combined)
            # Show only Merger output instead of the full response
            merger_output = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
            st.json(merger_output)

# ## --- Stage 3: Structure Creation --- that currently works perfectly
# def render_stage_3():
#     st.header("Stage 3: Ebook Structure Creation")
#     st.markdown("Define the core parameters for your ebook. The AI will generate a detailed skeleton, including chapter structure, narrative arc, and reference distribution.")

#     # Check if we're in edit mode
#     if 'edit_mode_stage_3' not in st.session_state:
#         st.session_state.edit_mode_stage_3 = False

#     # Disable sidebar navigation during edit mode
#     if st.session_state.edit_mode_stage_3:
#         st.warning("🔒 Modo de edición activo. Guarda o cancela los cambios antes de navegar.")

#     # --- GENERATION FORM ---
#     if not st.session_state.edit_mode_stage_3:
#         with st.form("structure_form"):
#             st.text_area(
#                 "Main Topics & Subtopics", 
#                 key='topic_input',
#                 help="Enter main topics, one per line. If 'AI Generates Subtopics' is unchecked, add subtopics indented below each main topic.",
#                 height=200
#             )
#             st.checkbox("AI Generates Subtopics", key='subtemas_enabled', help="Check this to let the AI generate subtopics based on the main topics you provide.")
            
#             cols = st.columns(2)
#             with cols[0]:
#                 st.slider("Reference Density", 1, 50, key='reference_count', help="Desired total number of references in the ebook.")
#             with cols[1]:
#                 st.select_slider(
#                     "Target Page Count", 
#                     options=["20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100+"],
#                     key='page_count',
#                     help="Estimated page range for the final ebook."
#                 )
            
#             submitted = st.form_submit_button(
#                 "Generate Ebook Skeleton", 
#                 use_container_width=True, 
#                 type="primary",
#                 disabled=(st.session_state.stage_3_status == 'in_progress')
#             )

#         # --- REGENERATION WARNING DIALOG ---
#         @st.dialog("Confirmar Regeneración")
#         def confirm_regeneration():
#             st.warning("Ya tienes un esqueleto que puedes editar. Regenerar lo reemplazará. ¿Continuar?")
#             col1, col2 = st.columns(2)
#             with col1:
#                 if st.button("Sí, Regenerar", type="primary", use_container_width=True):
#                     st.session_state.confirm_regen = True
#                     st.rerun()
#             with col2:
#                 if st.button("Cancelar", use_container_width=True):
#                     st.session_state.confirm_regen = False
#                     st.rerun()

#         # --- HANDLE FORM SUBMISSION ---
#         if submitted:
#             if not st.session_state.topic_input:
#                 st.warning("Please provide main topics before generating the skeleton.")
#                 return

#             # Check if skeleton already exists
#             if st.session_state.skeleton and 'confirm_regen' not in st.session_state:
#                 confirm_regeneration()
#                 return

#             # If user confirmed or first time generating
#             if st.session_state.get('confirm_regen', True):
#                 st.session_state.stage_3_status = 'in_progress'
                
#                 # Clear confirmation flag
#                 if 'confirm_regen' in st.session_state:
#                     del st.session_state.confirm_regen
                
#                 inputs = {
#                     "compendio": st.session_state.compendio_md,
#                     "projectBrief": st.session_state.project_brief_md,
#                     "topicInput": st.session_state.topic_input,
#                     "referenceCount": st.session_state.reference_count,
#                     "MapeoContenido": json.dumps(st.session_state.mapping_combined),
#                     "pageCount": st.session_state.page_count,
#                     "subtemas": not st.session_state.subtemas_enabled
#                 }
                
#                 st.info("Generating the ebook skeleton... This might take a moment.")
#                 stream_container = st.empty()
                
#                 result = process_wordware_api(APP_IDS["theme_selector"], inputs, stream_container)
                
#                 if result:
#                     st.session_state.skeleton = result
                    
#                     # Extract chapter sequence for Stage 4
#                     try:
#                         structure = result.get('EsqueletoMaestro', {}).get('esqueletoLogica', {}).get('estructura_capitulos', [])
#                         chapter_list = [f"capitulo_{i+1}" for i in range(len(structure))]
                        
#                         st.session_state.chapter_sequence = chapter_list
#                         st.session_state.stage_3_status = 'completed'
#                         st.success("Stage 3 Completed! Ebook skeleton generated successfully.")
#                     except Exception as e:
#                         st.session_state.stage_3_status = 'error'
#                         st.error(f"Could not parse chapter structure from skeleton: {e}")
#                         st.json(result)
#                 else:
#                     st.session_state.stage_3_status = 'error'
#                     st.error("Failed to generate ebook skeleton.")
#                 st.rerun()

#     # --- DISPLAY GENERATED SKELETON (View Mode) ---
#     if st.session_state.stage_3_status == 'completed' and not st.session_state.edit_mode_stage_3:
#         st.success("✅ Stage 3 is complete. You can now proceed to Stage 4.")
        
#         # Edit button
#         if st.button("✏️ Editar Esqueleto", use_container_width=True, type="secondary"):
#             st.session_state.edit_mode_stage_3 = True
#             # Initialize editing state with safe defaults
#             esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
#             st.session_state.edit_chapters = esqueleto.get('estructura_capitulos', [])
#             st.session_state.edit_subchapters = esqueleto.get('estructura_sub_capitulos', [])
#             st.session_state.edit_narrative = esqueleto.get('arco_narrativo', '')
            
#             # Parse metrics with safe defaults (metricas_estimadas is inside esqueletoLogica)
#             metricas = esqueleto.get('metricas_estimadas', {})
#             st.session_state.edit_total_words = metricas.get('palabras_totales', 1000) or 1000
#             st.session_state.edit_total_pages = metricas.get('paginas_totales', 10) or 10
#             st.session_state.edit_citas_por_cap = metricas.get('citas_por_capitulo', [])
#             st.session_state.edit_palabras_por_cap = metricas.get('palabras_totales_por_capitulo', [])
#             st.session_state.edit_paginas_por_cap = metricas.get('paginas_por_capitulo', [])
            
#             # Parse reference distribution
#             dist_refs = esqueleto.get('distribuicion_referencias', {})
#             st.session_state.edit_referencias_mapeo = dist_refs.get('referenciasMapeo', [])
            
#             st.rerun()
        
#         st.divider()
        
#         # Display skeleton in readable format
#         esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
#         chapters = esqueleto.get('estructura_capitulos', [])
#         subchapters = esqueleto.get('estructura_sub_capitulos', [])
#         narrative = esqueleto.get('arco_narrativo', '')
#         metricas = esqueleto.get('metricas_estimadas', {})
        
#         st.subheader("Estructura del Ebook")
        
#         # Display chapters with expandable subchapters
#         for i, chapter in enumerate(chapters, 1):
#             # Get subchapters for this chapter
#             chapter_subs = [s for s in subchapters if s.startswith(f"{i}.")]
            
#             with st.expander(f"**{chapter}**", expanded=False):
#                 if chapter_subs:
#                     for sub in chapter_subs:
#                         st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{sub}")
#                 else:
#                     st.write("*No hay subtemas definidos*")
        
#         st.divider()
        
#         st.subheader("Arco Narrativo")
#         st.write(narrative if narrative else "*No definido*")
        
#         st.divider()
        
#         st.subheader("Métricas Estimadas - Totales")
#         col1, col2 = st.columns(2)
#         with col1:
#             st.metric("Palabras Totales", metricas.get('palabras_totales', 'N/A'))
#         with col2:
#             st.metric("Páginas Totales", metricas.get('paginas_totales', 'N/A'))
        
#         st.divider()
        
#         st.subheader("Métricas por Capítulo")
        
#         col1, col2, col3 = st.columns(3)
        
#         with col1:
#             st.markdown("**Citas Esperadas**")
#             citas_por_cap = metricas.get('citas_por_capitulo', [])
#             if citas_por_cap:
#                 for item in citas_por_cap:
#                     st.write(f"• {item}")
#             else:
#                 st.write("*No definido*")
        
#         with col2:
#             st.markdown("**Palabras Estimadas**")
#             palabras_por_cap = metricas.get('palabras_totales_por_capitulo', [])
#             if palabras_por_cap:
#                 for item in palabras_por_cap:
#                     st.write(f"• {item}")
#             else:
#                 st.write("*No definido*")
        
#         with col3:
#             st.markdown("**Páginas Asignadas**")
#             paginas_por_cap = metricas.get('paginas_por_capitulo', [])
#             if paginas_por_cap:
#                 for item in paginas_por_cap:
#                     st.write(f"• {item}")
#             else:
#                 st.write("*No definido*")
        
#         st.divider()
        
#         st.subheader("Distribución de Referencias")
#         referencias_mapeo = esqueleto.get('distribuicion_referencias', {}).get('referenciasMapeo', [])
#         if referencias_mapeo:
#             for ref in referencias_mapeo:
#                 st.write(f"• {ref}")
#         else:
#             st.write("*No hay referencias mapeadas*")
        
#         st.divider()
        
#         st.info(f"El esqueleto define {len(st.session_state.chapter_sequence)} capítulos para generar.")

#     # --- EDIT MODE INTERFACE ---
#     if st.session_state.edit_mode_stage_3:
#         st.subheader("🔧 Editando Esqueleto")
        
#         # Initialize chapter count if needed
#         if 'edit_chapter_count' not in st.session_state:
#             st.session_state.edit_chapter_count = len(st.session_state.edit_chapters)
        
#         # Chapter management buttons
#         col1, col2 = st.columns([1, 1])
#         with col1:
#             if st.button("➕ Agregar Capítulo", use_container_width=True):
#                 st.session_state.edit_chapter_count += 1
#                 st.session_state.edit_chapters.append(f"{st.session_state.edit_chapter_count}. Nuevo Capítulo")
#                 st.rerun()
#         with col2:
#             if st.button("🗑️ Eliminar Último", use_container_width=True, disabled=(st.session_state.edit_chapter_count <= 1)):
#                 if st.session_state.edit_chapter_count > 1:
#                     st.session_state.edit_chapter_count -= 1
#                     st.session_state.edit_chapters.pop()
#                     st.rerun()
        
#         st.divider()
        
#         # Dynamic chapter editing fields with expandable subchapters
#         edited_chapters = []
#         edited_subchapters = []
        
#         for i in range(st.session_state.edit_chapter_count):
#             # Get current chapter title
#             current_title = st.session_state.edit_chapters[i] if i < len(st.session_state.edit_chapters) else f"{i+1}. Nuevo Capítulo"
#             title_text = current_title.split('.', 1)[1].strip() if '.' in current_title else current_title
            
#             # Chapter title input
#             chapter_title = st.text_input(
#                 f"Capítulo {i+1}",
#                 value=title_text,
#                 key=f"chapter_title_{i}"
#             )
#             edited_chapters.append(f"{i+1}. {chapter_title}")
            
#             # Subtopics in expander
#             with st.expander(f"Subtemas para {i+1}. {chapter_title}", expanded=False):
#                 st.caption("*No agregues numeración - se añadirá automáticamente*")
                
#                 # Get existing subtopics for this chapter
#                 existing_subs = [s for s in st.session_state.edit_subchapters if s.startswith(f"{i+1}.")]
#                 existing_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in existing_subs])
                
#                 subtopics_text = st.text_area(
#                     f"Subtemas",
#                     value=existing_text,
#                     height=150,
#                     key=f"subtopics_{i}",
#                     label_visibility="collapsed"
#                 )
                
#                 # Process and number subtopics
#                 if subtopics_text.strip():
#                     lines = [line.strip() for line in subtopics_text.split('\n') if line.strip()]
#                     for j, line in enumerate(lines, 1):
#                         # Strip any existing numbering
#                         clean_line = line
#                         if '.' in line:
#                             parts = line.split(' ', 1)
#                             if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
#                                 clean_line = parts[1]
                        
#                         edited_subchapters.append(f"{i+1}.{j} {clean_line}")
        
#         st.divider()
        
#         # Narrative arc editing
#         st.subheader("Arco Narrativo")
#         edited_narrative = st.text_area(
#             "Descripción del flujo narrativo del ebook",
#             value=st.session_state.edit_narrative,
#             height=150,
#             key="narrative_arc"
#         )
        
#         st.divider()
        
#         # Metrics editing
#         st.subheader("Métricas Estimadas")
#         col1, col2 = st.columns(2)
#         with col1:
#             edited_total_words = st.number_input(
#                 "Palabras Totales",
#                 min_value=100,
#                 value=int(st.session_state.edit_total_words),
#                 step=100,
#                 key="total_words"
#             )
#         with col2:
#             edited_total_pages = st.number_input(
#                 "Páginas Totales",
#                 min_value=1,
#                 value=int(st.session_state.edit_total_pages),
#                 step=1,
#                 key="total_pages"
#             )
        
#         st.markdown("#### Métricas por Capítulo")
#         st.caption("*Una línea por capítulo. Se actualizarán automáticamente si agregas/eliminas capítulos.*")
        
#         col1, col2, col3 = st.columns(3)
#         with col1:
#             st.markdown("**Citas Esperadas**")
#             citas_text = "\n".join(st.session_state.edit_citas_por_cap) if st.session_state.edit_citas_por_cap else ""
#             edited_citas = st.text_area(
#                 "Citas por capítulo",
#                 value=citas_text,
#                 height=150,
#                 key="citas_por_cap",
#                 label_visibility="collapsed",
#                 placeholder="Capítulo 1: X citas esperadas\nCapítulo 2: Y citas esperadas"
#             )
#         with col2:
#             st.markdown("**Palabras Estimadas**")
#             palabras_text = "\n".join(st.session_state.edit_palabras_por_cap) if st.session_state.edit_palabras_por_cap else ""
#             edited_palabras = st.text_area(
#                 "Palabras por capítulo",
#                 value=palabras_text,
#                 height=150,
#                 key="palabras_por_cap",
#                 label_visibility="collapsed",
#                 placeholder="Capítulo 1: X palabras estimadas\nCapítulo 2: Y palabras estimadas"
#             )
#         with col3:
#             st.markdown("**Páginas Asignadas**")
#             paginas_text = "\n".join(st.session_state.edit_paginas_por_cap) if st.session_state.edit_paginas_por_cap else ""
#             edited_paginas = st.text_area(
#                 "Páginas por capítulo",
#                 value=paginas_text,
#                 height=150,
#                 key="paginas_por_cap",
#                 label_visibility="collapsed",
#                 placeholder="Capítulo 1: X páginas asignadas\nCapítulo 2: Y páginas asignadas"
#             )
        
#         st.divider()
        
#         st.subheader("Distribución de Referencias")
#         st.caption("*Mapeo de referencias por capítulo. Una línea por capítulo.*")
#         referencias_text = "\n".join(st.session_state.edit_referencias_mapeo) if st.session_state.edit_referencias_mapeo else ""
#         edited_referencias = st.text_area(
#             "Referencias mapeadas",
#             value=referencias_text,
#             height=150,
#             key="referencias_mapeo",
#             placeholder="Capítulo 1: TAB-001, TAB-002\nCapítulo 2: TAB-003"
#         )
        
#         st.divider()
        
#         # Save/Cancel buttons
#         col1, col2 = st.columns(2)
#         with col1:
#             if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
#                 # Update skeleton with edited data
#                 esqueleto_logica = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
#                 esqueleto_logica['estructura_capitulos'] = edited_chapters
#                 esqueleto_logica['estructura_sub_capitulos'] = edited_subchapters
#                 esqueleto_logica['arco_narrativo'] = edited_narrative
                
#                 # Update metrics (metricas_estimadas is inside esqueletoLogica)
#                 metricas = esqueleto_logica.get('metricas_estimadas', {})
#                 metricas['palabras_totales'] = edited_total_words
#                 metricas['paginas_totales'] = edited_total_pages
                
#                 # Update per-chapter metrics (split by newlines, filter empty)
#                 metricas['citas_por_capitulo'] = [line.strip() for line in edited_citas.split('\n') if line.strip()]
#                 metricas['palabras_totales_por_capitulo'] = [line.strip() for line in edited_palabras.split('\n') if line.strip()]
#                 metricas['paginas_por_capitulo'] = [line.strip() for line in edited_paginas.split('\n') if line.strip()]
                
#                 # Update reference distribution
#                 dist_refs = esqueleto_logica.get('distribuicion_referencias', {})
#                 dist_refs['referenciasMapeo'] = [line.strip() for line in edited_referencias.split('\n') if line.strip()]
                
#                 # Rebuild chapter sequence
#                 st.session_state.chapter_sequence = [f"capitulo_{i+1}" for i in range(len(edited_chapters))]
                
#                 # Exit edit mode
#                 st.session_state.edit_mode_stage_3 = False
                
#                 # Clean up edit state
#                 for key in list(st.session_state.keys()):
#                     if key.startswith('edit_') or key.startswith('chapter_title_') or key.startswith('subtopics_'):
#                         del st.session_state[key]
                
#                 st.success("Esqueleto actualizado exitosamente!")
#                 st.rerun()
        
#         with col2:
#             if st.button("❌ Cancelar", use_container_width=True):
#                 # Confirmation dialog
#                 @st.dialog("¿Descartar cambios?")
#                 def confirm_cancel():
#                     st.warning("Los cambios no guardados se perderán. ¿Continuar?")
#                     col1, col2 = st.columns(2)
#                     with col1:
#                         if st.button("Sí, Descartar", type="primary", use_container_width=True):
#                             st.session_state.edit_mode_stage_3 = False
#                             # Clean up edit state
#                             for key in list(st.session_state.keys()):
#                                 if key.startswith('edit_') or key.startswith('chapter_title_') or key.startswith('subtopics_'):
#                                     del st.session_state[key]
#                             st.rerun()
#                     with col2:
#                         if st.button("No, Volver", use_container_width=True):
#                             st.rerun()
                
#                 confirm_cancel()

## --- Stage 3: Structure Creation (MODIFIED - Dynamic Reference Slider) ---
## --- Stage 3: Structure Creation (MODIFIED - Dynamic Citation Count Slider) ---
def render_stage_3():
    st.header("Stage 3: Ebook Structure Creation")
    st.markdown("Define the core parameters for your ebook. The AI will generate a detailed skeleton, including chapter structure, narrative arc, and reference distribution.")

    # Extract total citations from Stage 2 mapping for dynamic slider
    try:
        mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
        
        # If it's a string, parse it
        if isinstance(mapeo_contenido, str):
            mapeo_contenido = json.loads(mapeo_contenido)
        
        citas = mapeo_contenido.get('citas', {}).get('citas_en_texto', [])
        total_citations = len(citas) if citas else 50  # Fallback to 50 if empty
    except Exception as e:
        # If anything fails, default to 50
        total_citations = 50
        st.warning(f"Could not extract citation count, defaulting to max 50. Error: {e}")

    # Check if we're in edit mode
    if 'edit_mode_stage_3' not in st.session_state:
        st.session_state.edit_mode_stage_3 = False

    # Disable sidebar navigation during edit mode
    if st.session_state.edit_mode_stage_3:
        st.warning("🔒 Modo de edición activo. Guarda o cancela los cambios antes de navegar.")

    # --- GENERATION FORM ---
    if not st.session_state.edit_mode_stage_3:
        with st.form("structure_form"):
            st.text_area(
                "Main Topics & Subtopics", 
                key='topic_input',
                help="Enter main topics, one per line. If 'AI Generates Subtopics' is unchecked, add subtopics indented below each main topic.",
                height=200
            )
            st.checkbox("AI Generates Subtopics", key='subtemas_enabled', help="Check this to let the AI generate subtopics based on the main topics you provide.")
            
            cols = st.columns(2)
            with cols[0]:
                st.slider(
                    "Citation Density", 
                    min_value=1, 
                    max_value=max(total_citations, 1),
                    key='reference_count',
                    help=f"Desired total number of references in the ebook. ({total_citations} citations available from compendio)"
                )
            with cols[1]:
                st.select_slider(
                    "Target Page Count", 
                    options=["20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100+"],
                    key='page_count',
                    help="Estimated page range for the final ebook."
                )
            
            submitted = st.form_submit_button(
                "Generate Ebook Skeleton", 
                use_container_width=True, 
                type="primary",
                disabled=(st.session_state.stage_3_status == 'in_progress')
            )

        # --- REGENERATION WARNING DIALOG ---
        @st.dialog("Confirmar Regeneración")
        def confirm_regeneration():
            st.warning("Ya tienes un esqueleto que puedes editar. Regenerar lo reemplazará. ¿Continuar?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Sí, Regenerar", type="primary", use_container_width=True):
                    st.session_state.confirm_regen = True
                    st.rerun()
            with col2:
                if st.button("Cancelar", use_container_width=True):
                    st.session_state.confirm_regen = False
                    st.rerun()

        # --- HANDLE FORM SUBMISSION ---
        if submitted:
            if not st.session_state.topic_input:
                st.warning("Please provide main topics before generating the skeleton.")
                return

            # Check if skeleton already exists
            if st.session_state.skeleton and 'confirm_regen' not in st.session_state:
                confirm_regeneration()
                return

            # If user confirmed or first time generating
            if st.session_state.get('confirm_regen', True):
                st.session_state.stage_3_status = 'in_progress'
                
                # Clear confirmation flag
                if 'confirm_regen' in st.session_state:
                    del st.session_state.confirm_regen
                
                inputs = {
                    "compendio": st.session_state.compendio_md,
                    "projectBrief": st.session_state.project_brief_md,
                    "topicInput": st.session_state.topic_input,
                    "referenceCount": st.session_state.reference_count,
                    "MapeoContenido": json.dumps(st.session_state.mapping_combined),
                    "pageCount": st.session_state.page_count,
                    "subtemas": not st.session_state.subtemas_enabled
                }
                
                st.info("Generating the ebook skeleton... This might take a moment.")
                stream_container = st.empty()
                
                result = process_wordware_api(APP_IDS["theme_selector"], inputs, stream_container)
                
                if result:
                    st.session_state.skeleton = result
                    
                    # Extract chapter sequence for Stage 4
                    try:
                        structure = result.get('EsqueletoMaestro', {}).get('esqueletoLogica', {}).get('estructura_capitulos', [])
                        chapter_list = [f"capitulo_{i+1}" for i in range(len(structure))]
                        
                        st.session_state.chapter_sequence = chapter_list
                        st.session_state.stage_3_status = 'completed'
                        st.success("Stage 3 Completed! Ebook skeleton generated successfully.")
                    except Exception as e:
                        st.session_state.stage_3_status = 'error'
                        st.error(f"Could not parse chapter structure from skeleton: {e}")
                        st.json(result)
                else:
                    st.session_state.stage_3_status = 'error'
                    st.error("Failed to generate ebook skeleton.")
                st.rerun()

    # --- DISPLAY GENERATED SKELETON (View Mode) ---
    if st.session_state.stage_3_status == 'completed' and not st.session_state.edit_mode_stage_3:
        st.success("✅ Stage 3 is complete. You can now proceed to Stage 4.")
        
        # Edit button
        if st.button("✏️ Editar Esqueleto", use_container_width=True, type="secondary"):
            st.session_state.edit_mode_stage_3 = True
            # Initialize editing state with safe defaults
            esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
            st.session_state.edit_chapters = esqueleto.get('estructura_capitulos', [])
            st.session_state.edit_subchapters = esqueleto.get('estructura_sub_capitulos', [])
            st.session_state.edit_narrative = esqueleto.get('arco_narrativo', '')
            
            # Parse metrics with safe defaults (metricas_estimadas is inside esqueletoLogica)
            metricas = esqueleto.get('metricas_estimadas', {})
            st.session_state.edit_total_words = metricas.get('palabras_totales', 1000) or 1000
            st.session_state.edit_total_pages = metricas.get('paginas_totales', 10) or 10
            st.session_state.edit_citas_por_cap = metricas.get('citas_por_capitulo', [])
            st.session_state.edit_palabras_por_cap = metricas.get('palabras_totales_por_capitulo', [])
            st.session_state.edit_paginas_por_cap = metricas.get('paginas_por_capitulo', [])
            
            # Parse reference distribution
            dist_refs = esqueleto.get('distribuicion_referencias', {})
            st.session_state.edit_referencias_mapeo = dist_refs.get('referenciasMapeo', [])
            
            st.rerun()
        
        st.divider()
        
        # Display skeleton in readable format
        esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
        chapters = esqueleto.get('estructura_capitulos', [])
        subchapters = esqueleto.get('estructura_sub_capitulos', [])
        narrative = esqueleto.get('arco_narrativo', '')
        metricas = esqueleto.get('metricas_estimadas', {})
        
        st.subheader("Estructura del Ebook")
        
        # Display chapters with expandable subchapters
        for i, chapter in enumerate(chapters, 1):
            # Get subchapters for this chapter
            chapter_subs = [s for s in subchapters if s.startswith(f"{i}.")]
            
            with st.expander(f"**{chapter}**", expanded=False):
                if chapter_subs:
                    for sub in chapter_subs:
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{sub}")
                else:
                    st.write("*No hay subtemas definidos*")
        
        st.divider()
        
        st.subheader("Arco Narrativo")
        st.write(narrative if narrative else "*No definido*")
        
        st.divider()
        
        st.subheader("Métricas Estimadas - Totales")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Palabras Totales", metricas.get('palabras_totales', 'N/A'))
        with col2:
            st.metric("Páginas Totales", metricas.get('paginas_totales', 'N/A'))
        
        st.divider()
        
        st.subheader("Métricas por Capítulo")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Citas Esperadas**")
            citas_por_cap = metricas.get('citas_por_capitulo', [])
            if citas_por_cap:
                for item in citas_por_cap:
                    st.write(f"• {item}")
            else:
                st.write("*No definido*")
        
        with col2:
            st.markdown("**Palabras Estimadas**")
            palabras_por_cap = metricas.get('palabras_totales_por_capitulo', [])
            if palabras_por_cap:
                for item in palabras_por_cap:
                    st.write(f"• {item}")
            else:
                st.write("*No definido*")
        
        with col3:
            st.markdown("**Páginas Asignadas**")
            paginas_por_cap = metricas.get('paginas_por_capitulo', [])
            if paginas_por_cap:
                for item in paginas_por_cap:
                    st.write(f"• {item}")
            else:
                st.write("*No definido*")
        
        st.divider()
        
        st.subheader("Distribución de Referencias")
        referencias_mapeo = esqueleto.get('distribuicion_referencias', {}).get('referenciasMapeo', [])
        if referencias_mapeo:
            for ref in referencias_mapeo:
                st.write(f"• {ref}")
        else:
            st.write("*No hay referencias mapeadas*")
        
        st.divider()
        
        st.info(f"El esqueleto define {len(st.session_state.chapter_sequence)} capítulos para generar.")

    # --- EDIT MODE INTERFACE ---
    if st.session_state.edit_mode_stage_3:
        st.subheader("🔧 Editando Esqueleto")
        
        # Initialize chapter count if needed
        if 'edit_chapter_count' not in st.session_state:
            st.session_state.edit_chapter_count = len(st.session_state.edit_chapters)
        
        # Chapter management buttons
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("➕ Agregar Capítulo", use_container_width=True):
                st.session_state.edit_chapter_count += 1
                st.session_state.edit_chapters.append(f"{st.session_state.edit_chapter_count}. Nuevo Capítulo")
                st.rerun()
        with col2:
            if st.button("🗑️ Eliminar Último", use_container_width=True, disabled=(st.session_state.edit_chapter_count <= 1)):
                if st.session_state.edit_chapter_count > 1:
                    st.session_state.edit_chapter_count -= 1
                    st.session_state.edit_chapters.pop()
                    st.rerun()
        
        st.divider()
        
        # Dynamic chapter editing fields with expandable subchapters
        edited_chapters = []
        edited_subchapters = []
        
        for i in range(st.session_state.edit_chapter_count):
            # Get current chapter title
            current_title = st.session_state.edit_chapters[i] if i < len(st.session_state.edit_chapters) else f"{i+1}. Nuevo Capítulo"
            title_text = current_title.split('.', 1)[1].strip() if '.' in current_title else current_title
            
            # Chapter title input
            chapter_title = st.text_input(
                f"Capítulo {i+1}",
                value=title_text,
                key=f"chapter_title_{i}"
            )
            edited_chapters.append(f"{i+1}. {chapter_title}")
            
            # Subtopics in expander
            with st.expander(f"Subtemas para {i+1}. {chapter_title}", expanded=False):
                st.caption("*No agregues numeración - se añadirá automáticamente*")
                
                # Get existing subtopics for this chapter
                existing_subs = [s for s in st.session_state.edit_subchapters if s.startswith(f"{i+1}.")]
                existing_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in existing_subs])
                
                subtopics_text = st.text_area(
                    f"Subtemas",
                    value=existing_text,
                    height=150,
                    key=f"subtopics_{i}",
                    label_visibility="collapsed"
                )
                
                # Process and number subtopics
                if subtopics_text.strip():
                    lines = [line.strip() for line in subtopics_text.split('\n') if line.strip()]
                    for j, line in enumerate(lines, 1):
                        # Strip any existing numbering
                        clean_line = line
                        if '.' in line:
                            parts = line.split(' ', 1)
                            if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
                                clean_line = parts[1]
                        
                        edited_subchapters.append(f"{i+1}.{j} {clean_line}")
        
        st.divider()
        
        # Narrative arc editing
        st.subheader("Arco Narrativo")
        edited_narrative = st.text_area(
            "Descripción del flujo narrativo del ebook",
            value=st.session_state.edit_narrative,
            height=150,
            key="narrative_arc"
        )
        
        st.divider()
        
        # Metrics editing
        st.subheader("Métricas Estimadas")
        col1, col2 = st.columns(2)
        with col1:
            edited_total_words = st.number_input(
                "Palabras Totales",
                min_value=100,
                value=int(st.session_state.edit_total_words),
                step=100,
                key="total_words"
            )
        with col2:
            edited_total_pages = st.number_input(
                "Páginas Totales",
                min_value=1,
                value=int(st.session_state.edit_total_pages),
                step=1,
                key="total_pages"
            )
        
        st.markdown("#### Métricas por Capítulo")
        st.caption("*Una línea por capítulo. Se actualizarán automáticamente si agregas/eliminas capítulos.*")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Citas Esperadas**")
            citas_text = "\n".join(st.session_state.edit_citas_por_cap) if st.session_state.edit_citas_por_cap else ""
            edited_citas = st.text_area(
                "Citas por capítulo",
                value=citas_text,
                height=150,
                key="citas_por_cap",
                label_visibility="collapsed",
                placeholder="Capítulo 1: X citas esperadas\nCapítulo 2: Y citas esperadas"
            )
        with col2:
            st.markdown("**Palabras Estimadas**")
            palabras_text = "\n".join(st.session_state.edit_palabras_por_cap) if st.session_state.edit_palabras_por_cap else ""
            edited_palabras = st.text_area(
                "Palabras por capítulo",
                value=palabras_text,
                height=150,
                key="palabras_por_cap",
                label_visibility="collapsed",
                placeholder="Capítulo 1: X palabras estimadas\nCapítulo 2: Y palabras estimadas"
            )
        with col3:
            st.markdown("**Páginas Asignadas**")
            paginas_text = "\n".join(st.session_state.edit_paginas_por_cap) if st.session_state.edit_paginas_por_cap else ""
            edited_paginas = st.text_area(
                "Páginas por capítulo",
                value=paginas_text,
                height=150,
                key="paginas_por_cap",
                label_visibility="collapsed",
                placeholder="Capítulo 1: X páginas asignadas\nCapítulo 2: Y páginas asignadas"
            )
        
        st.divider()
        
        st.subheader("Distribución de Referencias")
        st.caption("*Mapeo de referencias por capítulo. Una línea por capítulo.*")
        referencias_text = "\n".join(st.session_state.edit_referencias_mapeo) if st.session_state.edit_referencias_mapeo else ""
        edited_referencias = st.text_area(
            "Referencias mapeadas",
            value=referencias_text,
            height=150,
            key="referencias_mapeo",
            placeholder="Capítulo 1: TAB-001, TAB-002\nCapítulo 2: TAB-003"
        )
        
        st.divider()
        
        # Save/Cancel buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Guardar Cambios", type="primary", use_container_width=True):
                # Update skeleton with edited data
                esqueleto_logica = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                esqueleto_logica['estructura_capitulos'] = edited_chapters
                esqueleto_logica['estructura_sub_capitulos'] = edited_subchapters
                esqueleto_logica['arco_narrativo'] = edited_narrative
                
                # Update metrics (metricas_estimadas is inside esqueletoLogica)
                metricas = esqueleto_logica.get('metricas_estimadas', {})
                metricas['palabras_totales'] = edited_total_words
                metricas['paginas_totales'] = edited_total_pages
                
                # Update per-chapter metrics (split by newlines, filter empty)
                metricas['citas_por_capitulo'] = [line.strip() for line in edited_citas.split('\n') if line.strip()]
                metricas['palabras_totales_por_capitulo'] = [line.strip() for line in edited_palabras.split('\n') if line.strip()]
                metricas['paginas_por_capitulo'] = [line.strip() for line in edited_paginas.split('\n') if line.strip()]
                
                # Update reference distribution
                dist_refs = esqueleto_logica.get('distribuicion_referencias', {})
                dist_refs['referenciasMapeo'] = [line.strip() for line in edited_referencias.split('\n') if line.strip()]
                
                # Rebuild chapter sequence
                st.session_state.chapter_sequence = [f"capitulo_{i+1}" for i in range(len(edited_chapters))]
                
                # Exit edit mode
                st.session_state.edit_mode_stage_3 = False
                
                # Clean up edit state
                for key in list(st.session_state.keys()):
                    if key.startswith('edit_') or key.startswith('chapter_title_') or key.startswith('subtopics_'):
                        del st.session_state[key]
                
                st.success("Esqueleto actualizado exitosamente!")
                st.rerun()
        
        with col2:
            if st.button("❌ Cancelar", use_container_width=True):
                # Confirmation dialog
                @st.dialog("¿Descartar cambios?")
                def confirm_cancel():
                    st.warning("Los cambios no guardados se perderán. ¿Continuar?")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Sí, Descartar", type="primary", use_container_width=True):
                            st.session_state.edit_mode_stage_3 = False
                            # Clean up edit state
                            for key in list(st.session_state.keys()):
                                if key.startswith('edit_') or key.startswith('chapter_title_') or key.startswith('subtopics_'):
                                    del st.session_state[key]
                            st.rerun()
                    with col2:
                        if st.button("No, Volver", use_container_width=True):
                            st.rerun()
                
                confirm_cancel()
                
# # # ## --- Stage 4: Chapter Creation --- Individual Chapter Parameters.  
# # # def render_stage_4():
# # #     st.header("Stage 4: Chapter Generation")
# # #     st.markdown("Generate chapters in any order. Edit parameters before generation and regenerate any chapter as needed.")

# # #     if not st.session_state.chapter_sequence:
# # #         st.warning("No chapters defined in the skeleton from Stage 3.")
# # #         return

# # #     # Display progress
# # #     total_chapters = len(st.session_state.chapter_sequence)
# # #     completed_chapters = len([c for c in st.session_state.chapter_sequence if c in st.session_state.generated_chapters])
    
# # #     if completed_chapters >= total_chapters and not st.session_state.book_complete:
# # #         st.session_state.book_complete = True
# # #         st.session_state.stage_4_status = 'completed'
    
# # #     st.progress(completed_chapters / total_chapters, text=f"{completed_chapters}/{total_chapters} Chapters Generated")

# # #     if 'editing_params_for' not in st.session_state:
# # #         st.session_state.editing_params_for = None

# # #     if 'edit_modes' not in st.session_state:
# # #         st.session_state.edit_modes = {}

# # #     st.divider()

# # #     esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
    
# # #     for idx, chapter_id in enumerate(st.session_state.chapter_sequence):
# # #         chapter_number = idx + 1
        
# # #         chapter_title = esqueleto.get('estructura_capitulos', [])[chapter_number - 1] if chapter_number <= len(esqueleto.get('estructura_capitulos', [])) else f"{chapter_number}. Sin título"
# # #         chapter_exists = chapter_id in st.session_state.generated_chapters
# # #         is_editing_this = st.session_state.editing_params_for == chapter_id
# # #         is_content_edit_mode = st.session_state.edit_modes.get(chapter_id, False)
        
# # #         status = "✅ Generado" if chapter_exists else "⚪ Pendiente"
        
# # #         st.subheader(f"{status} {chapter_title}")
        
# # #         # --- PARAMETER EDITING SECTION ---
# # #         show_params = (not chapter_exists) or is_editing_this
        
# # #         if show_params:
# # #             chapter_subtopics = [s for s in esqueleto.get('estructura_sub_capitulos', []) if s.startswith(f"{chapter_number}.")]
# # #             arco_narrativo = esqueleto.get('arco_narrativo', '')
            
# # #             custom_params_key = f"custom_params_{chapter_id}"
# # #             if custom_params_key in st.session_state:
# # #                 chapter_title = st.session_state[custom_params_key]['chapter_title']
# # #                 chapter_subtopics = st.session_state[custom_params_key]['subtopics']
# # #                 arco_narrativo = st.session_state[custom_params_key]['arco_narrativo']
            
# # #             with st.expander("📋 Parámetros del Capítulo", expanded=is_editing_this):
# # #                 if not is_editing_this:
# # #                     st.markdown(f"**Título:** {chapter_title}")
# # #                     st.markdown("**Subtemas:**")
# # #                     for sub in chapter_subtopics:
# # #                         st.write(f"  • {sub}")
# # #                     st.markdown("**Arco Narrativo:**")
# # #                     st.write(arco_narrativo)
                    
# # #                     if st.button("✏️ Editar Parámetros", key=f"edit_params_{chapter_id}"):
# # #                         st.session_state.editing_params_for = chapter_id
# # #                         st.rerun()
# # #                 else:
# # #                     st.caption("*Edita los parámetros para este capítulo.*")
                    
# # #                     title_text = chapter_title.split('.', 1)[1].strip() if '.' in chapter_title else chapter_title
# # #                     edited_title = st.text_input("Título del Capítulo", value=title_text, key=f"param_title_{chapter_id}")
                    
# # #                     st.markdown("**Subtemas** *(No agregues numeración)*")
# # #                     subtopics_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in chapter_subtopics])
# # #                     edited_subtopics_text = st.text_area("Subtemas", value=subtopics_text, height=150, key=f"param_subtopics_{chapter_id}", label_visibility="collapsed")
                    
# # #                     edited_arco = st.text_area("Arco Narrativo", value=arco_narrativo, height=100, key=f"param_arco_{chapter_id}")
                    
# # #                     col1, col2 = st.columns(2)
# # #                     with col1:
# # #                         button_text = "🔄 Regenerar con Estos Parámetros" if chapter_exists else "💾 Guardar Parámetros"
                        
# # #                         if st.button(button_text, type="primary", use_container_width=True, key=f"save_params_{chapter_id}"):
# # #                             edited_subtopics = []
# # #                             if edited_subtopics_text.strip():
# # #                                 lines = [line.strip() for line in edited_subtopics_text.split('\n') if line.strip()]
# # #                                 for j, line in enumerate(lines, 1):
# # #                                     clean_line = line
# # #                                     if '.' in line:
# # #                                         parts = line.split(' ', 1)
# # #                                         if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
# # #                                             clean_line = parts[1]
# # #                                     edited_subtopics.append(f"{chapter_number}.{j} {clean_line}")
                            
# # #                             st.session_state[custom_params_key] = {
# # #                                 'chapter_title': f"{chapter_number}. {edited_title}",
# # #                                 'subtopics': edited_subtopics,
# # #                                 'arco_narrativo': edited_arco
# # #                             }
                            
# # #                             st.session_state.editing_params_for = None
                            
# # #                             if chapter_exists:
# # #                                 # REGENERATE NOW
# # #                                 status_placeholder = st.empty()
# # #                                 status_placeholder.info(f"🔄 Regenerando {chapter_id}...")
                                
# # #                                 skeleton_to_send = json.loads(json.dumps(st.session_state.skeleton))
# # #                                 esqueleto_copy = skeleton_to_send.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                                
# # #                                 if 'estructura_capitulos' in esqueleto_copy and chapter_number <= len(esqueleto_copy['estructura_capitulos']):
# # #                                     esqueleto_copy['estructura_capitulos'][chapter_number - 1] = st.session_state[custom_params_key]['chapter_title']
                                
# # #                                 if 'estructura_sub_capitulos' in esqueleto_copy:
# # #                                     esqueleto_copy['estructura_sub_capitulos'] = [s for s in esqueleto_copy['estructura_sub_capitulos'] if not s.startswith(f"{chapter_number}.")]
# # #                                     esqueleto_copy['estructura_sub_capitulos'].extend(st.session_state[custom_params_key]['subtopics'])
# # #                                     esqueleto_copy['estructura_sub_capitulos'].sort()
                                
# # #                                 esqueleto_copy['arco_narrativo'] = st.session_state[custom_params_key]['arco_narrativo']
                                
# # #                                 # Get Merger output from mapping_combined
# # #                                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                                
# # #                                 inputs = {
# # #                                     "Skeleton": json.dumps(skeleton_to_send.get('EsqueletoMaestro', {})),
# # #                                     "CompendioMd": st.session_state.compendio_md,
# # #                                     "previous_context": "",
# # #                                     "capituloConstruir": chapter_id,
# # #                                     "mapeoContenido": json.dumps(mapeo_contenido)
# # #                                 }
                                
# # #                                 stream_container = st.empty()
# # #                                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                                
# # #                                 status_placeholder.empty()
                                
# # #                                 if result:
# # #                                     generated_chapter = result.get('generatedChapter', {})
# # #                                     chapter_data = generated_chapter.get('chapterTitle', {})
                                    
# # #                                     if chapter_data:
# # #                                         chapter_storage = chapter_data.copy()
# # #                                         chapter_storage['custom_params_used'] = st.session_state[custom_params_key]
# # #                                         st.session_state.generated_chapters[chapter_id] = chapter_storage
                                        
# # #                                         if chapter_id not in st.session_state.chapters_completed:
# # #                                             st.session_state.chapters_completed.append(chapter_id)
                                        
# # #                                         st.success(f"✅ {chapter_id} regenerado exitosamente!")
# # #                                         st.balloons()
# # #                                         time.sleep(2)
# # #                                         st.rerun()
# # #                                     else:
# # #                                         st.error("❌ Respuesta malformada del API")
# # #                                 else:
# # #                                     st.error("❌ Fallo en la llamada al API")
# # #                             else:
# # #                                 st.success("✅ Parámetros guardados!")
# # #                                 st.rerun()
                    
# # #                     with col2:
# # #                         if st.button("❌ Cancelar", use_container_width=True, key=f"cancel_params_{chapter_id}"):
# # #                             st.session_state.editing_params_for = None
# # #                             st.rerun()
        
# # #         # --- GENERATION BUTTON ---
# # #         if not chapter_exists:
# # #             if st.button("▶️ Generar Capítulo", type="primary", use_container_width=True, key=f"gen_{chapter_id}"):
# # #                 status_placeholder = st.empty()
# # #                 status_placeholder.info(f"🔄 Generando {chapter_id}...")
                
# # #                 custom_params_key = f"custom_params_{chapter_id}"
# # #                 skeleton_to_send = json.loads(json.dumps(st.session_state.skeleton))
                
# # #                 if custom_params_key in st.session_state:
# # #                     esqueleto_copy = skeleton_to_send.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                    
# # #                     if 'estructura_capitulos' in esqueleto_copy and chapter_number <= len(esqueleto_copy['estructura_capitulos']):
# # #                         esqueleto_copy['estructura_capitulos'][chapter_number - 1] = st.session_state[custom_params_key]['chapter_title']
                    
# # #                     if 'estructura_sub_capitulos' in esqueleto_copy:
# # #                         esqueleto_copy['estructura_sub_capitulos'] = [s for s in esqueleto_copy['estructura_sub_capitulos'] if not s.startswith(f"{chapter_number}.")]
# # #                         esqueleto_copy['estructura_sub_capitulos'].extend(st.session_state[custom_params_key]['subtopics'])
# # #                         esqueleto_copy['estructura_sub_capitulos'].sort()
                    
# # #                     esqueleto_copy['arco_narrativo'] = st.session_state[custom_params_key]['arco_narrativo']
                
# # #                 # Get Merger output from mapping_combined
# # #                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                
# # #                 inputs = {
# # #                     "Skeleton": json.dumps(skeleton_to_send.get('EsqueletoMaestro', {})),
# # #                     "CompendioMd": st.session_state.compendio_md,
# # #                     "previous_context": "",
# # #                     "capituloConstruir": chapter_id,
# # #                     "mapeoContenido": json.dumps(mapeo_contenido)
# # #                 }
                
# # #                 stream_container = st.empty()
# # #                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                
# # #                 status_placeholder.empty()
                
# # #                 if result:
# # #                     generated_chapter = result.get('generatedChapter', {})
# # #                     chapter_data = generated_chapter.get('chapterTitle', {})
                    
# # #                     if chapter_data:
# # #                         chapter_storage = chapter_data.copy()
# # #                         if custom_params_key in st.session_state:
# # #                             chapter_storage['custom_params_used'] = st.session_state[custom_params_key]
                        
# # #                         st.session_state.generated_chapters[chapter_id] = chapter_storage
                        
# # #                         if chapter_id not in st.session_state.chapters_completed:
# # #                             st.session_state.chapters_completed.append(chapter_id)
                        
# # #                         st.success(f"✅ {chapter_id} generado exitosamente!")
# # #                         st.balloons()
# # #                         time.sleep(2)
# # #                         st.rerun()
# # #                     else:
# # #                         st.error("❌ Respuesta malformada del API")
# # #                 else:
# # #                     st.error("❌ Fallo en la llamada al API")
        
# # #         # --- CHAPTER REVIEW ---
# # #         if chapter_exists:
# # #             chapter_data = st.session_state.generated_chapters[chapter_id]
            
# # #             with st.expander(f"📖 Ver Capítulo Generado", expanded=is_content_edit_mode):
# # #                 col1, col2, col3 = st.columns([2, 1, 1])
                
# # #                 with col1:
# # #                     st.metric("Word Count", chapter_data.get('conteo_palabras', 'N/A'))
                
# # #                 with col2:
# # #                     edit_button_label = "💾 Guardar Cambios" if is_content_edit_mode else "✏️ Editar Contenido"
# # #                     if st.button(edit_button_label, key=f"edit_content_btn_{chapter_id}"):
# # #                         if is_content_edit_mode:
# # #                             edited_content = st.session_state.get(f"edit_content_{chapter_id}", "")
# # #                             st.session_state.generated_chapters[chapter_id]['contenido_capitulo'] = edited_content
# # #                             word_count = len(edited_content.split())
# # #                             st.session_state.generated_chapters[chapter_id]['conteo_palabras'] = word_count
# # #                             st.session_state.edit_modes[chapter_id] = False
# # #                             st.success("✅ Cambios guardados!")
# # #                             st.rerun()
# # #                         else:
# # #                             st.session_state.edit_modes[chapter_id] = True
# # #                             st.rerun()
                
# # #                 with col3:
# # #                     if st.button("🔄 Regenerar", key=f"regen_{chapter_id}"):
# # #                         st.session_state.editing_params_for = chapter_id
# # #                         st.rerun()
                
# # #                 st.markdown("#### Referencias Usadas")
# # #                 st.write(chapter_data.get('referencias_usadas', []))
                
# # #                 if 'custom_params_used' in chapter_data:
# # #                     st.markdown("#### ⚙️ Parámetros Personalizados")
# # #                     st.json(chapter_data['custom_params_used'])
                
# # #                 st.markdown("#### Contenido del Capítulo")
# # #                 if is_content_edit_mode:
# # #                     st.text_area("Editar contenido:", value=chapter_data.get('contenido_capitulo', ''), height=400, key=f"edit_content_{chapter_id}")
# # #                 else:
# # #                     st.markdown(chapter_data.get('contenido_capitulo', 'No content found.'))
        
# # #         st.divider()
    
# # #     if completed_chapters >= total_chapters:
# # #         st.success("✅ Todos los capítulos generados. Procede a Stage 5.")

# ## --- Stage 4: Chapter Creation (MODIFIED VERSION - Cumulative Skeleton Edits) ---
# def render_stage_4():
#     st.header("Stage 4: Chapter Generation")
#     st.markdown("Generate chapters in any order. Edit parameters before generation and regenerate any chapter as needed.")

#     if not st.session_state.chapter_sequence:
#         st.warning("No chapters defined in the skeleton from Stage 3.")
#         return

#     # Display progress
#     total_chapters = len(st.session_state.chapter_sequence)
#     completed_chapters = len([c for c in st.session_state.chapter_sequence if c in st.session_state.generated_chapters])
    
#     if completed_chapters >= total_chapters and not st.session_state.book_complete:
#         st.session_state.book_complete = True
#         st.session_state.stage_4_status = 'completed'
    
#     st.progress(completed_chapters / total_chapters, text=f"{completed_chapters}/{total_chapters} Chapters Generated")

#     if 'editing_params_for' not in st.session_state:
#         st.session_state.editing_params_for = None

#     if 'edit_modes' not in st.session_state:
#         st.session_state.edit_modes = {}

#     st.divider()

#     esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
    
#     for idx, chapter_id in enumerate(st.session_state.chapter_sequence):
#         chapter_number = idx + 1
        
#         chapter_title = esqueleto.get('estructura_capitulos', [])[chapter_number - 1] if chapter_number <= len(esqueleto.get('estructura_capitulos', [])) else f"{chapter_number}. Sin título"
#         chapter_exists = chapter_id in st.session_state.generated_chapters
#         is_editing_this = st.session_state.editing_params_for == chapter_id
#         is_content_edit_mode = st.session_state.edit_modes.get(chapter_id, False)
        
#         status = "✅ Generado" if chapter_exists else "⚪ Pendiente"
        
#         st.subheader(f"{status} {chapter_title}")
        
#         # --- PARAMETER EDITING SECTION ---
#         show_params = (not chapter_exists) or is_editing_this
        
#         if show_params:
#             chapter_subtopics = [s for s in esqueleto.get('estructura_sub_capitulos', []) if s.startswith(f"{chapter_number}.")]
#             arco_narrativo = esqueleto.get('arco_narrativo', '')
            
#             # REMOVED: custom_params_key logic - now we read directly from skeleton
            
#             with st.expander("📋 Parámetros del Capítulo", expanded=is_editing_this):
#                 if not is_editing_this:
#                     st.markdown(f"**Título:** {chapter_title}")
#                     st.markdown("**Subtemas:**")
#                     for sub in chapter_subtopics:
#                         st.write(f"  • {sub}")
#                     st.markdown("**Arco Narrativo:**")
#                     st.write(arco_narrativo)
                    
#                     if st.button("✏️ Editar Parámetros", key=f"edit_params_{chapter_id}"):
#                         st.session_state.editing_params_for = chapter_id
#                         st.rerun()
#                 else:
#                     st.caption("*Edita los parámetros para este capítulo. Los cambios se guardarán en el esqueleto maestro.*")
                    
#                     title_text = chapter_title.split('.', 1)[1].strip() if '.' in chapter_title else chapter_title
#                     edited_title = st.text_input("Título del Capítulo", value=title_text, key=f"param_title_{chapter_id}")
                    
#                     st.markdown("**Subtemas** *(No agregues numeración)*")
#                     subtopics_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in chapter_subtopics])
#                     edited_subtopics_text = st.text_area("Subtemas", value=subtopics_text, height=150, key=f"param_subtopics_{chapter_id}", label_visibility="collapsed")
                    
#                     edited_arco = st.text_area("Arco Narrativo", value=arco_narrativo, height=100, key=f"param_arco_{chapter_id}")
                    
#                     col1, col2 = st.columns(2)
#                     with col1:
#                         button_text = "🔄 Regenerar con Estos Parámetros" if chapter_exists else "💾 Guardar Parámetros"
                        
#                         if st.button(button_text, type="primary", use_container_width=True, key=f"save_params_{chapter_id}"):
#                             # Process edited subtopics
#                             edited_subtopics = []
#                             if edited_subtopics_text.strip():
#                                 lines = [line.strip() for line in edited_subtopics_text.split('\n') if line.strip()]
#                                 for j, line in enumerate(lines, 1):
#                                     clean_line = line
#                                     if '.' in line:
#                                         parts = line.split(' ', 1)
#                                         if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
#                                             clean_line = parts[1]
#                                     edited_subtopics.append(f"{chapter_number}.{j} {clean_line}")
                            
#                             # MODIFIED: Update the main skeleton directly instead of custom_params
#                             esqueleto_logica = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                            
#                             # Update chapter title in main skeleton
#                             if 'estructura_capitulos' in esqueleto_logica and chapter_number <= len(esqueleto_logica['estructura_capitulos']):
#                                 esqueleto_logica['estructura_capitulos'][chapter_number - 1] = f"{chapter_number}. {edited_title}"
                            
#                             # Update subtopics in main skeleton
#                             if 'estructura_sub_capitulos' in esqueleto_logica:
#                                 # Remove old subtopics for this chapter
#                                 esqueleto_logica['estructura_sub_capitulos'] = [
#                                     s for s in esqueleto_logica['estructura_sub_capitulos'] 
#                                     if not s.startswith(f"{chapter_number}.")
#                                 ]
#                                 # Add new subtopics
#                                 esqueleto_logica['estructura_sub_capitulos'].extend(edited_subtopics)
#                                 esqueleto_logica['estructura_sub_capitulos'].sort()
                            
#                             # Update narrative arc in main skeleton
#                             esqueleto_logica['arco_narrativo'] = edited_arco
                            
#                             st.session_state.editing_params_for = None
                            
#                             if chapter_exists:
#                                 # REGENERATE NOW - using the main skeleton (no temporary copy needed)
#                                 status_placeholder = st.empty()
#                                 status_placeholder.info(f"🔄 Regenerando {chapter_id}...")
                                
#                                 # Get Merger output from mapping_combined
#                                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                                
#                                 inputs = {
#                                     "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
#                                     "CompendioMd": st.session_state.compendio_md,
#                                     "previous_context": "",
#                                     "capituloConstruir": chapter_id,
#                                     "mapeoContenido": json.dumps(mapeo_contenido)
#                                 }
                                
#                                 stream_container = st.empty()
#                                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                                
#                                 status_placeholder.empty()
                                
#                                 if result:
#                                     generated_chapter = result.get('generatedChapter', {})
#                                     chapter_data = generated_chapter.get('chapterTitle', {})
                                    
#                                     if chapter_data:
#                                         # MODIFIED: No longer storing custom_params_used
#                                         st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                                        
#                                         if chapter_id not in st.session_state.chapters_completed:
#                                             st.session_state.chapters_completed.append(chapter_id)
                                        
#                                         st.success(f"✅ {chapter_id} regenerado exitosamente!")
#                                         st.balloons()
#                                         time.sleep(2)
#                                         st.rerun()
#                                     else:
#                                         st.error("❌ Respuesta malformada del API")
#                                 else:
#                                     st.error("❌ Fallo en la llamada al API")
#                             else:
#                                 st.success("✅ Parámetros guardados en el esqueleto maestro!")
#                                 st.rerun()
                    
#                     with col2:
#                         if st.button("❌ Cancelar", use_container_width=True, key=f"cancel_params_{chapter_id}"):
#                             st.session_state.editing_params_for = None
#                             st.rerun()
        
#         # --- GENERATION BUTTON ---
#         if not chapter_exists:
#             if st.button("▶️ Generar Capítulo", type="primary", use_container_width=True, key=f"gen_{chapter_id}"):
#                 status_placeholder = st.empty()
#                 status_placeholder.info(f"🔄 Generando {chapter_id}...")
                
#                 # MODIFIED: No custom_params logic - use main skeleton directly
#                 # Get Merger output from mapping_combined
#                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                
#                 inputs = {
#                     "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
#                     "CompendioMd": st.session_state.compendio_md,
#                     "previous_context": "",
#                     "capituloConstruir": chapter_id,
#                     "mapeoContenido": json.dumps(mapeo_contenido)
#                 }
                
#                 stream_container = st.empty()
#                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                
#                 status_placeholder.empty()
                
#                 if result:
#                     generated_chapter = result.get('generatedChapter', {})
#                     chapter_data = generated_chapter.get('chapterTitle', {})
                    
#                     if chapter_data:
#                         # MODIFIED: No custom_params storage
#                         st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                        
#                         if chapter_id not in st.session_state.chapters_completed:
#                             st.session_state.chapters_completed.append(chapter_id)
                        
#                         st.success(f"✅ {chapter_id} generado exitosamente!")
#                         st.balloons()
#                         time.sleep(2)
#                         st.rerun()
#                     else:
#                         st.error("❌ Respuesta malformada del API")
#                 else:
#                     st.error("❌ Fallo en la llamada al API")
        
#         # --- CHAPTER REVIEW ---
#         if chapter_exists:
#             chapter_data = st.session_state.generated_chapters[chapter_id]
            
#             with st.expander(f"📖 Ver Capítulo Generado", expanded=is_content_edit_mode):
#                 col1, col2, col3 = st.columns([2, 1, 1])
                
#                 with col1:
#                     st.metric("Word Count", chapter_data.get('conteo_palabras', 'N/A'))
                
#                 with col2:
#                     edit_button_label = "💾 Guardar Cambios" if is_content_edit_mode else "✏️ Editar Contenido"
#                     if st.button(edit_button_label, key=f"edit_content_btn_{chapter_id}"):
#                         if is_content_edit_mode:
#                             edited_content = st.session_state.get(f"edit_content_{chapter_id}", "")
#                             st.session_state.generated_chapters[chapter_id]['contenido_capitulo'] = edited_content
#                             word_count = len(edited_content.split())
#                             st.session_state.generated_chapters[chapter_id]['conteo_palabras'] = word_count
#                             st.session_state.edit_modes[chapter_id] = False
#                             st.success("✅ Cambios guardados!")
#                             st.rerun()
#                         else:
#                             st.session_state.edit_modes[chapter_id] = True
#                             st.rerun()
                
#                 with col3:
#                     if st.button("🔄 Regenerar", key=f"regen_{chapter_id}"):
#                         st.session_state.editing_params_for = chapter_id
#                         st.rerun()
                
#                 st.markdown("#### Referencias Usadas")
#                 st.write(chapter_data.get('referencias_usadas', []))
                
#                 # REMOVED: Display of custom_params_used since we no longer store them
                
#                 st.markdown("#### Contenido del Capítulo")
#                 if is_content_edit_mode:
#                     st.text_area("Editar contenido:", value=chapter_data.get('contenido_capitulo', ''), height=400, key=f"edit_content_{chapter_id}")
#                 else:
#                     st.markdown(chapter_data.get('contenido_capitulo', 'No content found.'))
        
#         st.divider()
    
#     if completed_chapters >= total_chapters:
#         st.success("✅ Todos los capítulos generados. Procede a Stage 5.")

# # # ## --- Stage 4: Chapter Creation (ENHANCED VERSION - Full Parameter Editing) ---
# # # def render_stage_4():
# # #     st.header("Stage 4: Chapter Generation")
# # #     st.markdown("Generate chapters in any order. Edit parameters before generation and regenerate any chapter as needed.")

# # #     if not st.session_state.chapter_sequence:
# # #         st.warning("No chapters defined in the skeleton from Stage 3.")
# # #         return

# # #     # Display progress
# # #     total_chapters = len(st.session_state.chapter_sequence)
# # #     completed_chapters = len([c for c in st.session_state.chapter_sequence if c in st.session_state.generated_chapters])
    
# # #     if completed_chapters >= total_chapters and not st.session_state.book_complete:
# # #         st.session_state.book_complete = True
# # #         st.session_state.stage_4_status = 'completed'
    
# # #     st.progress(completed_chapters / total_chapters, text=f"{completed_chapters}/{total_chapters} Chapters Generated")

# # #     if 'editing_params_for' not in st.session_state:
# # #         st.session_state.editing_params_for = None

# # #     if 'edit_modes' not in st.session_state:
# # #         st.session_state.edit_modes = {}

# # #     st.divider()

# # #     esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
    
# # #     for idx, chapter_id in enumerate(st.session_state.chapter_sequence):
# # #         chapter_number = idx + 1
# # #         chapter_index = idx  # 0-based index for array access
        
# # #         chapter_title = esqueleto.get('estructura_capitulos', [])[chapter_number - 1] if chapter_number <= len(esqueleto.get('estructura_capitulos', [])) else f"{chapter_number}. Sin título"
# # #         chapter_exists = chapter_id in st.session_state.generated_chapters
# # #         is_editing_this = st.session_state.editing_params_for == chapter_id
# # #         is_content_edit_mode = st.session_state.edit_modes.get(chapter_id, False)
        
# # #         status = "✅ Generado" if chapter_exists else "⚪ Pendiente"
        
# # #         st.subheader(f"{status} {chapter_title}")
        
# # #         # --- PARAMETER EDITING SECTION ---
# # #         show_params = (not chapter_exists) or is_editing_this
        
# # #         if show_params:
# # #             chapter_subtopics = [s for s in esqueleto.get('estructura_sub_capitulos', []) if s.startswith(f"{chapter_number}.")]
# # #             arco_narrativo = esqueleto.get('arco_narrativo', '')
            
# # #             # Extract chapter-specific metrics
# # #             metricas = esqueleto.get('metricas_estimadas', {})
            
# # #             # Helper function to parse metric value from string like "Capítulo 2: 11 páginas asignadas"
# # #             def extract_metric_value(metric_array, chapter_num, default=0):
# # #                 try:
# # #                     for entry in metric_array:
# # #                         if entry.startswith(f"Capítulo {chapter_num}:"):
# # #                             # Extract number from string
# # #                             import re
# # #                             numbers = re.findall(r'\d+', entry.split(':')[1])
# # #                             if numbers:
# # #                                 return int(numbers[0])
# # #                 except:
# # #                     pass
# # #                 return default
            
# # #             # Helper function to extract references from string like "Capítulo 2: REF-001, REF-003"
# # #             def extract_references(ref_array, chapter_num, default=""):
# # #                 try:
# # #                     for entry in ref_array:
# # #                         if entry.startswith(f"Capítulo {chapter_num}:"):
# # #                             # Extract everything after the colon
# # #                             return entry.split(':', 1)[1].strip()
# # #                 except:
# # #                     pass
# # #                 return default
            
# # #             current_paginas = extract_metric_value(metricas.get('paginas_por_capitulo', []), chapter_number, 10)
# # #             current_palabras = extract_metric_value(metricas.get('palabras_totales_por_capitulo', []), chapter_number, 1000)
# # #             current_citas = extract_metric_value(metricas.get('citas_por_capitulo', []), chapter_number, 5)
# # #             current_referencias = extract_references(esqueleto.get('distribuicion_referencias', {}).get('referenciasMapeo', []), chapter_number, "")
            
# # #             with st.expander("📋 Parámetros del Capítulo", expanded=is_editing_this):
# # #                 if not is_editing_this:
# # #                     st.markdown(f"**Título:** {chapter_title}")
# # #                     st.markdown("**Subtemas:**")
# # #                     for sub in chapter_subtopics:
# # #                         st.write(f"  • {sub}")
# # #                     st.markdown("**Métricas:**")
# # #                     st.write(f"  • Páginas: {current_paginas}")
# # #                     st.write(f"  • Palabras: {current_palabras}")
# # #                     st.write(f"  • Citas esperadas: {current_citas}")
# # #                     st.markdown("**Referencias asignadas:**")
# # #                     st.write(f"  {current_referencias if current_referencias else 'Ninguna'}")
                    
# # #                     if st.button("✏️ Editar Parámetros", key=f"edit_params_{chapter_id}"):
# # #                         st.session_state.editing_params_for = chapter_id
# # #                         st.rerun()
# # #                 else:
# # #                     st.caption("*Edita los parámetros para este capítulo. Los cambios se guardarán en el esqueleto maestro.*")
                    
# # #                     # Chapter Title
# # #                     title_text = chapter_title.split('.', 1)[1].strip() if '.' in chapter_title else chapter_title
# # #                     edited_title = st.text_input("Título del Capítulo", value=title_text, key=f"param_title_{chapter_id}")
                    
# # #                     # Subtopics
# # #                     st.markdown("**Subtemas** *(No agregues numeración)*")
# # #                     subtopics_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in chapter_subtopics])
# # #                     edited_subtopics_text = st.text_area("Subtemas", value=subtopics_text, height=150, key=f"param_subtopics_{chapter_id}", label_visibility="collapsed")
                    
# # #                     st.divider()
                    
# # #                     # Metrics
# # #                     st.markdown("**Métricas del Capítulo**")
# # #                     col1, col2, col3 = st.columns(3)
# # #                     with col1:
# # #                         edited_paginas = st.number_input("Páginas Asignadas", min_value=1, value=current_paginas, step=1, key=f"param_paginas_{chapter_id}")
# # #                     with col2:
# # #                         edited_palabras = st.number_input("Palabras Estimadas", min_value=100, value=current_palabras, step=100, key=f"param_palabras_{chapter_id}")
# # #                     with col3:
# # #                         edited_citas = st.number_input("Citas Esperadas", min_value=0, value=current_citas, step=1, key=f"param_citas_{chapter_id}")
                    
# # #                     st.divider()
                    
# # #                     # References
# # #                     st.markdown("**Referencias Asignadas**")
# # #                     st.caption("*Formato: REF-001, REF-002, REF-003 (separadas por comas)*")
# # #                     edited_referencias = st.text_input("Referencias", value=current_referencias, key=f"param_referencias_{chapter_id}", label_visibility="collapsed")
                    
# # #                     # Validate reference format
# # #                     ref_warning = ""
# # #                     if edited_referencias.strip():
# # #                         refs = [r.strip() for r in edited_referencias.split(',')]
# # #                         invalid_refs = [r for r in refs if not r.startswith('REF-')]
# # #                         if invalid_refs:
# # #                             ref_warning = f"⚠️ Referencias con formato incorrecto: {', '.join(invalid_refs)}"
                    
# # #                     if ref_warning:
# # #                         st.warning(ref_warning)
                    
# # #                     st.divider()
                    
# # #                     # Narrative Arc (optional, can be hidden if too much)
# # #                     with st.expander("Arco Narrativo (Opcional)", expanded=False):
# # #                         edited_arco = st.text_area("Arco Narrativo", value=arco_narrativo, height=100, key=f"param_arco_{chapter_id}")
                    
# # #                     col1, col2 = st.columns(2)
# # #                     with col1:
# # #                         button_text = "🔄 Regenerar con Estos Parámetros" if chapter_exists else "💾 Guardar Parámetros"
                        
# # #                         if st.button(button_text, type="primary", use_container_width=True, key=f"save_params_{chapter_id}"):
# # #                             # Process edited subtopics
# # #                             edited_subtopics = []
# # #                             if edited_subtopics_text.strip():
# # #                                 lines = [line.strip() for line in edited_subtopics_text.split('\n') if line.strip()]
# # #                                 for j, line in enumerate(lines, 1):
# # #                                     clean_line = line
# # #                                     if '.' in line:
# # #                                         parts = line.split(' ', 1)
# # #                                         if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
# # #                                             clean_line = parts[1]
# # #                                     edited_subtopics.append(f"{chapter_number}.{j} {clean_line}")
                            
# # #                             # Update the main skeleton directly
# # #                             esqueleto_logica = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                            
# # #                             # Update chapter title
# # #                             if 'estructura_capitulos' in esqueleto_logica and chapter_number <= len(esqueleto_logica['estructura_capitulos']):
# # #                                 esqueleto_logica['estructura_capitulos'][chapter_index] = f"{chapter_number}. {edited_title}"
                            
# # #                             # Update subtopics
# # #                             if 'estructura_sub_capitulos' in esqueleto_logica:
# # #                                 esqueleto_logica['estructura_sub_capitulos'] = [
# # #                                     s for s in esqueleto_logica['estructura_sub_capitulos'] 
# # #                                     if not s.startswith(f"{chapter_number}.")
# # #                                 ]
# # #                                 esqueleto_logica['estructura_sub_capitulos'].extend(edited_subtopics)
# # #                                 esqueleto_logica['estructura_sub_capitulos'].sort()
                            
# # #                             # Update metrics
# # #                             metricas_est = esqueleto_logica.get('metricas_estimadas', {})
# # #                             if 'paginas_por_capitulo' in metricas_est and chapter_index < len(metricas_est['paginas_por_capitulo']):
# # #                                 metricas_est['paginas_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_paginas} páginas asignadas"
# # #                             if 'palabras_totales_por_capitulo' in metricas_est and chapter_index < len(metricas_est['palabras_totales_por_capitulo']):
# # #                                 metricas_est['palabras_totales_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_palabras} palabras estimadas"
# # #                             if 'citas_por_capitulo' in metricas_est and chapter_index < len(metricas_est['citas_por_capitulo']):
# # #                                 metricas_est['citas_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_citas} citas esperadas"
                            
# # #                             # Update references
# # #                             dist_refs = esqueleto_logica.get('distribuicion_referencias', {})
# # #                             if 'referenciasMapeo' in dist_refs and chapter_index < len(dist_refs['referenciasMapeo']):
# # #                                 dist_refs['referenciasMapeo'][chapter_index] = f"Capítulo {chapter_number}: {edited_referencias}"
                            
# # #                             # Update narrative arc if it was expanded/edited
# # #                             if f"param_arco_{chapter_id}" in st.session_state:
# # #                                 esqueleto_logica['arco_narrativo'] = st.session_state[f"param_arco_{chapter_id}"]
                            
# # #                             st.session_state.editing_params_for = None
                            
# # #                             if chapter_exists:
# # #                                 # REGENERATE NOW
# # #                                 status_placeholder = st.empty()
# # #                                 status_placeholder.info(f"🔄 Regenerando {chapter_id}...")
                                
# # #                                 # Get Merger output from mapping_combined
# # #                                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                                
# # #                                 inputs = {
# # #                                     "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
# # #                                     "CompendioMd": st.session_state.compendio_md,
# # #                                     "previous_context": "",
# # #                                     "capituloConstruir": chapter_id,
# # #                                     "mapeoContenido": json.dumps(mapeo_contenido)
# # #                                 }
                                
# # #                                 stream_container = st.empty()
# # #                                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                                
# # #                                 status_placeholder.empty()
                                
# # #                                 if result:
# # #                                     generated_chapter = result.get('generatedChapter', {})
# # #                                     chapter_data = generated_chapter.get('chapterTitle', {})
                                    
# # #                                     if chapter_data:
# # #                                         st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                                        
# # #                                         if chapter_id not in st.session_state.chapters_completed:
# # #                                             st.session_state.chapters_completed.append(chapter_id)
                                        
# # #                                         st.success(f"✅ {chapter_id} regenerado exitosamente!")
# # #                                         st.balloons()
# # #                                         time.sleep(2)
# # #                                         st.rerun()
# # #                                     else:
# # #                                         st.error("❌ Respuesta malformada del API")
# # #                                 else:
# # #                                     st.error("❌ Fallo en la llamada al API")
# # #                             else:
# # #                                 st.success("✅ Parámetros guardados en el esqueleto maestro!")
# # #                                 st.rerun()
                    
# # #                     with col2:
# # #                         if st.button("❌ Cancelar", use_container_width=True, key=f"cancel_params_{chapter_id}"):
# # #                             st.session_state.editing_params_for = None
# # #                             st.rerun()
        
# # #         # --- GENERATION BUTTON ---
# # #         if not chapter_exists:
# # #             if st.button("▶️ Generar Capítulo", type="primary", use_container_width=True, key=f"gen_{chapter_id}"):
# # #                 status_placeholder = st.empty()
# # #                 status_placeholder.info(f"🔄 Generando {chapter_id}...")
                
# # #                 # Get Merger output from mapping_combined
# # #                 mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                
# # #                 inputs = {
# # #                     "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
# # #                     "CompendioMd": st.session_state.compendio_md,
# # #                     "previous_context": "",
# # #                     "capituloConstruir": chapter_id,
# # #                     "mapeoContenido": json.dumps(mapeo_contenido)
# # #                 }
                
# # #                 stream_container = st.empty()
# # #                 result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                
# # #                 status_placeholder.empty()
                
# # #                 if result:
# # #                     generated_chapter = result.get('generatedChapter', {})
# # #                     chapter_data = generated_chapter.get('chapterTitle', {})
                    
# # #                     if chapter_data:
# # #                         st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                        
# # #                         if chapter_id not in st.session_state.chapters_completed:
# # #                             st.session_state.chapters_completed.append(chapter_id)
                        
# # #                         st.success(f"✅ {chapter_id} generado exitosamente!")
# # #                         st.balloons()
# # #                         time.sleep(2)
# # #                         st.rerun()
# # #                     else:
# # #                         st.error("❌ Respuesta malformada del API")
# # #                 else:
# # #                     st.error("❌ Fallo en la llamada al API")
        
# # #         # --- CHAPTER REVIEW ---
# # #         if chapter_exists:
# # #             chapter_data = st.session_state.generated_chapters[chapter_id]
            
# # #             with st.expander(f"📖 Ver Capítulo Generado", expanded=is_content_edit_mode):
# # #                 col1, col2, col3 = st.columns([2, 1, 1])
                
# # #                 with col1:
# # #                     st.metric("Word Count", chapter_data.get('conteo_palabras', 'N/A'))
                
# # #                 with col2:
# # #                     edit_button_label = "💾 Guardar Cambios" if is_content_edit_mode else "✏️ Editar Contenido"
# # #                     if st.button(edit_button_label, key=f"edit_content_btn_{chapter_id}"):
# # #                         if is_content_edit_mode:
# # #                             edited_content = st.session_state.get(f"edit_content_{chapter_id}", "")
# # #                             st.session_state.generated_chapters[chapter_id]['contenido_capitulo'] = edited_content
# # #                             word_count = len(edited_content.split())
# # #                             st.session_state.generated_chapters[chapter_id]['conteo_palabras'] = word_count
# # #                             st.session_state.edit_modes[chapter_id] = False
# # #                             st.success("✅ Cambios guardados!")
# # #                             st.rerun()
# # #                         else:
# # #                             st.session_state.edit_modes[chapter_id] = True
# # #                             st.rerun()
                
# # #                 with col3:
# # #                     if st.button("🔄 Regenerar", key=f"regen_{chapter_id}"):
# # #                         st.session_state.editing_params_for = chapter_id
# # #                         st.rerun()
                
# # #                 st.markdown("#### Referencias Usadas")
# # #                 st.write(chapter_data.get('referencias_usadas', []))
                
# # #                 st.markdown("#### Contenido del Capítulo")
# # #                 if is_content_edit_mode:
# # #                     st.text_area("Editar contenido:", value=chapter_data.get('contenido_capitulo', ''), height=400, key=f"edit_content_{chapter_id}")
# # #                 else:
# # #                     st.markdown(chapter_data.get('contenido_capitulo', 'No content found.'))
        
# # #         st.divider()
    
# # #     if completed_chapters >= total_chapters:
# # #         st.success("✅ Todos los capítulos generados. Procede a Stage 5.")

## --- Stage 4: Chapter Creation (ENHANCED - Full Parameter Editing + Auto Arco Narrativo) ---
def render_stage_4():
    st.header("Stage 4: Chapter Generation")
    st.markdown("Generate chapters in any order. Edit parameters before generation and regenerate any chapter as needed.")

    if not st.session_state.chapter_sequence:
        st.warning("No chapters defined in the skeleton from Stage 3.")
        return

    # Display progress
    total_chapters = len(st.session_state.chapter_sequence)
    completed_chapters = len([c for c in st.session_state.chapter_sequence if c in st.session_state.generated_chapters])
    
    if completed_chapters >= total_chapters and not st.session_state.book_complete:
        st.session_state.book_complete = True
        st.session_state.stage_4_status = 'completed'
    
    st.progress(completed_chapters / total_chapters, text=f"{completed_chapters}/{total_chapters} Chapters Generated")

    if 'editing_params_for' not in st.session_state:
        st.session_state.editing_params_for = None

    if 'edit_modes' not in st.session_state:
        st.session_state.edit_modes = {}

    st.divider()

    esqueleto = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
    
    for idx, chapter_id in enumerate(st.session_state.chapter_sequence):
        chapter_number = idx + 1
        chapter_index = idx  # 0-based index for array access
        
        chapter_title = esqueleto.get('estructura_capitulos', [])[chapter_number - 1] if chapter_number <= len(esqueleto.get('estructura_capitulos', [])) else f"{chapter_number}. Sin título"
        chapter_exists = chapter_id in st.session_state.generated_chapters
        is_editing_this = st.session_state.editing_params_for == chapter_id
        is_content_edit_mode = st.session_state.edit_modes.get(chapter_id, False)
        
        status = "✅ Generado" if chapter_exists else "⚪ Pendiente"
        
        st.subheader(f"{status} {chapter_title}")
        
        # --- PARAMETER EDITING SECTION ---
        show_params = (not chapter_exists) or is_editing_this
        
        if show_params:
            chapter_subtopics = [s for s in esqueleto.get('estructura_sub_capitulos', []) if s.startswith(f"{chapter_number}.")]
            arco_narrativo = esqueleto.get('arco_narrativo', '')
            
            # Extract chapter-specific metrics
            metricas = esqueleto.get('metricas_estimadas', {})
            
            # Helper function to parse metric value from string like "Capítulo 2: 11 páginas asignadas"
            def extract_metric_value(metric_array, chapter_num, default=0):
                try:
                    for entry in metric_array:
                        if entry.startswith(f"Capítulo {chapter_num}:"):
                            # Extract number from string
                            import re
                            numbers = re.findall(r'\d+', entry.split(':')[1])
                            if numbers:
                                return int(numbers[0])
                except:
                    pass
                return default
            
            # Helper function to extract references from string like "Capítulo 2: REF-001, REF-003"
            def extract_references(ref_array, chapter_num, default=""):
                try:
                    for entry in ref_array:
                        if entry.startswith(f"Capítulo {chapter_num}:"):
                            # Extract everything after the colon
                            return entry.split(':', 1)[1].strip()
                except:
                    pass
                return default
            
            current_paginas = extract_metric_value(metricas.get('paginas_por_capitulo', []), chapter_number, 10)
            current_palabras = extract_metric_value(metricas.get('palabras_totales_por_capitulo', []), chapter_number, 1000)
            current_citas = extract_metric_value(metricas.get('citas_por_capitulo', []), chapter_number, 5)
            current_referencias = extract_references(esqueleto.get('distribuicion_referencias', {}).get('referenciasMapeo', []), chapter_number, "")
            
            with st.expander("📋 Parámetros del Capítulo", expanded=is_editing_this):
                if not is_editing_this:
                    st.markdown(f"**Título:** {chapter_title}")
                    st.markdown("**Subtemas:**")
                    for sub in chapter_subtopics:
                        st.write(f"  • {sub}")
                    st.markdown("**Métricas:**")
                    st.write(f"  • Páginas: {current_paginas}")
                    st.write(f"  • Palabras: {current_palabras}")
                    st.write(f"  • Citas esperadas: {current_citas}")
                    st.markdown("**Referencias asignadas:**")
                    st.write(f"  {current_referencias if current_referencias else 'Ninguna'}")
                    
                    if st.button("✏️ Editar Parámetros", key=f"edit_params_{chapter_id}"):
                        st.session_state.editing_params_for = chapter_id
                        st.rerun()
                else:
                    st.caption("*Edita los parámetros para este capítulo. Los cambios se guardarán en el esqueleto maestro.*")
                    
                    # Chapter Title
                    title_text = chapter_title.split('.', 1)[1].strip() if '.' in chapter_title else chapter_title
                    edited_title = st.text_input("Título del Capítulo", value=title_text, key=f"param_title_{chapter_id}")
                    
                    # Subtopics
                    st.markdown("**Subtemas** *(No agregues numeración)*")
                    subtopics_text = "\n".join([s.split(' ', 1)[1] if ' ' in s else s for s in chapter_subtopics])
                    edited_subtopics_text = st.text_area("Subtemas", value=subtopics_text, height=150, key=f"param_subtopics_{chapter_id}", label_visibility="collapsed")
                    
                    st.divider()
                    
                    # Metrics
                    st.markdown("**Métricas del Capítulo**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        edited_paginas = st.number_input("Páginas Asignadas", min_value=1, value=current_paginas, step=1, key=f"param_paginas_{chapter_id}")
                    with col2:
                        edited_palabras = st.number_input("Palabras Estimadas", min_value=100, value=current_palabras, step=100, key=f"param_palabras_{chapter_id}")
                    with col3:
                        edited_citas = st.number_input("Citas Esperadas", min_value=0, value=current_citas, step=1, key=f"param_citas_{chapter_id}")
                    
                    st.divider()
                    
                    # References
                    st.markdown("**Referencias Asignadas**")
                    st.caption("*Formato: REF-001, REF-002, REF-003 (separadas por comas)*")
                    edited_referencias = st.text_input("Referencias", value=current_referencias, key=f"param_referencias_{chapter_id}", label_visibility="collapsed")
                    
                    # Validate reference format
                    ref_warning = ""
                    if edited_referencias.strip():
                        refs = [r.strip() for r in edited_referencias.split(',')]
                        invalid_refs = [r for r in refs if not r.startswith('REF-')]
                        if invalid_refs:
                            ref_warning = f"⚠️ Referencias con formato incorrecto: {', '.join(invalid_refs)}"
                    
                    if ref_warning:
                        st.warning(ref_warning)
                    
                    st.divider()
                    
                    # Arco Narrativo with Auto-Update Button
                    st.markdown("**Arco Narrativo**")
                    col_arco1, col_arco2 = st.columns([3, 1])
                    with col_arco2:
                        if st.button("🔄 Auto-actualizar", key=f"auto_arco_{chapter_id}", help="Regenera el arco narrativo basado en la estructura actual de capítulos y subtemas", use_container_width=True):
                            with st.spinner("Generando nuevo arco narrativo..."):
                                # Build hybrid structure: current edits + saved skeleton
                                esqueleto_base = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                                
                                # Get saved values
                                saved_chapters = esqueleto_base.get('estructura_capitulos', []).copy()
                                saved_subchapters = esqueleto_base.get('estructura_sub_capitulos', []).copy()
                                current_arco = esqueleto_base.get('arco_narrativo', '')
                                
                                # Get current edited values from form fields
                                edited_title_text = st.session_state.get(f"param_title_{chapter_id}", "")
                                edited_subtopics_raw = st.session_state.get(f"param_subtopics_{chapter_id}", "")
                                
                                # Process current chapter's edited title
                                if edited_title_text:
                                    if chapter_index < len(saved_chapters):
                                        saved_chapters[chapter_index] = f"{chapter_number}. {edited_title_text}"
                                
                                # Process current chapter's edited subtopics
                                if edited_subtopics_raw:
                                    # Remove old subtopics for this chapter
                                    saved_subchapters = [s for s in saved_subchapters if not s.startswith(f"{chapter_number}.")]
                                    
                                    # Add new edited subtopics
                                    lines = [line.strip() for line in edited_subtopics_raw.split('\n') if line.strip()]
                                    for j, line in enumerate(lines, 1):
                                        clean_line = line
                                        if '.' in line:
                                            parts = line.split(' ', 1)
                                            if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
                                                clean_line = parts[1]
                                        saved_subchapters.append(f"{chapter_number}.{j} {clean_line}")
                                    
                                    saved_subchapters.sort()
                                
                                inputs = {
                                    "estructura_capitulos": saved_chapters,
                                    "estructura_sub_capitulos": saved_subchapters,
                                    "previous_arco": current_arco
                                }
                                
                                result = process_wordware_api(APP_IDS["arcoNarrativo"], inputs)
                                
                                if result:
                                    # Handle unstructured output like Stage 5
                                    new_arco = ""
                                    if isinstance(result, dict):
                                        # Get the first string value from the dictionary
                                        for key, value in result.items():
                                            if isinstance(value, str):
                                                new_arco = value
                                                break
                                        else:
                                            # If no string values found, convert entire dict to string
                                            new_arco = str(result)
                                    else:
                                        new_arco = result
                                    
                                    if new_arco:
                                        # Update the skeleton
                                        esqueleto_base['arco_narrativo'] = new_arco
                                        #Also update the widget state so text area shows new value
                                        st.session_state[f"param_arco_{chapter_id}"] = new_arco
                                        st.success("✅ Arco narrativo actualizado!")
                                        st.rerun()
                                    else:
                                        st.error("❌ No se pudo generar el arco narrativo")
                                else:
                                    st.error("❌ Error en la llamada al API")
                    
                    with col_arco1:
                        edited_arco = st.text_area("Descripción del arco narrativo", value=arco_narrativo, height=120, key=f"param_arco_{chapter_id}", label_visibility="collapsed")
                    
                    st.divider()
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        button_text = "🔄 Regenerar con Estos Parámetros" if chapter_exists else "💾 Guardar Parámetros"
                        
                        if st.button(button_text, type="primary", use_container_width=True, key=f"save_params_{chapter_id}"):
                            # Process edited subtopics
                            edited_subtopics = []
                            if edited_subtopics_text.strip():
                                lines = [line.strip() for line in edited_subtopics_text.split('\n') if line.strip()]
                                for j, line in enumerate(lines, 1):
                                    clean_line = line
                                    if '.' in line:
                                        parts = line.split(' ', 1)
                                        if len(parts) > 1 and parts[0].replace('.', '').replace(' ', '').isdigit():
                                            clean_line = parts[1]
                                    edited_subtopics.append(f"{chapter_number}.{j} {clean_line}")
                            
                            # Update the main skeleton directly
                            esqueleto_logica = st.session_state.skeleton.get('EsqueletoMaestro', {}).get('esqueletoLogica', {})
                            
                            # Update chapter title
                            if 'estructura_capitulos' in esqueleto_logica and chapter_number <= len(esqueleto_logica['estructura_capitulos']):
                                esqueleto_logica['estructura_capitulos'][chapter_index] = f"{chapter_number}. {edited_title}"
                            
                            # Update subtopics
                            if 'estructura_sub_capitulos' in esqueleto_logica:
                                esqueleto_logica['estructura_sub_capitulos'] = [
                                    s for s in esqueleto_logica['estructura_sub_capitulos'] 
                                    if not s.startswith(f"{chapter_number}.")
                                ]
                                esqueleto_logica['estructura_sub_capitulos'].extend(edited_subtopics)
                                esqueleto_logica['estructura_sub_capitulos'].sort()
                            
                            # Update metrics
                            metricas_est = esqueleto_logica.get('metricas_estimadas', {})
                            if 'paginas_por_capitulo' in metricas_est and chapter_index < len(metricas_est['paginas_por_capitulo']):
                                metricas_est['paginas_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_paginas} páginas asignadas"
                            if 'palabras_totales_por_capitulo' in metricas_est and chapter_index < len(metricas_est['palabras_totales_por_capitulo']):
                                metricas_est['palabras_totales_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_palabras} palabras estimadas"
                            if 'citas_por_capitulo' in metricas_est and chapter_index < len(metricas_est['citas_por_capitulo']):
                                metricas_est['citas_por_capitulo'][chapter_index] = f"Capítulo {chapter_number}: {edited_citas} citas esperadas"
                            
                            # Update references
                            dist_refs = esqueleto_logica.get('distribuicion_referencias', {})
                            if 'referenciasMapeo' in dist_refs and chapter_index < len(dist_refs['referenciasMapeo']):
                                dist_refs['referenciasMapeo'][chapter_index] = f"Capítulo {chapter_number}: {edited_referencias}"
                            
                            # Update narrative arc
                            esqueleto_logica['arco_narrativo'] = edited_arco
                            
                            st.session_state.editing_params_for = None
                            
                            if chapter_exists:
                                # REGENERATE NOW
                                status_placeholder = st.empty()
                                status_placeholder.info(f"🔄 Regenerando {chapter_id}...")
                                
                                # Get Merger output from mapping_combined
                                mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                                
                                inputs = {
                                    "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
                                    "CompendioMd": st.session_state.compendio_md,
                                    "previous_context": "",
                                    "capituloConstruir": chapter_id,
                                    "mapeoContenido": json.dumps(mapeo_contenido)
                                }
                                
                                stream_container = st.empty()
                                result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                                
                                status_placeholder.empty()
                                
                                if result:
                                    generated_chapter = result.get('generatedChapter', {})
                                    chapter_data = generated_chapter.get('chapterTitle', {})
                                    
                                    if chapter_data:
                                        st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                                        
                                        if chapter_id not in st.session_state.chapters_completed:
                                            st.session_state.chapters_completed.append(chapter_id)
                                        
                                        st.success(f"✅ {chapter_id} regenerado exitosamente!")
                                        st.balloons()
                                        time.sleep(2)
                                        st.rerun()
                                    else:
                                        st.error("❌ Respuesta malformada del API")
                                else:
                                    st.error("❌ Fallo en la llamada al API")
                            else:
                                st.success("✅ Parámetros guardados en el esqueleto maestro!")
                                st.rerun()
                    
                    with col2:
                        if st.button("❌ Cancelar", use_container_width=True, key=f"cancel_params_{chapter_id}"):
                            st.session_state.editing_params_for = None
                            st.rerun()
        
        # --- GENERATION BUTTON ---
        if not chapter_exists:
            if st.button("▶️ Generar Capítulo", type="primary", use_container_width=True, key=f"gen_{chapter_id}"):
                status_placeholder = st.empty()
                status_placeholder.info(f"🔄 Generando {chapter_id}...")
                
                # Get Merger output from mapping_combined
                mapeo_contenido = st.session_state.mapping_combined.get('Merger', {}).get('output', st.session_state.mapping_combined)
                
                inputs = {
                    "Skeleton": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {})),
                    "CompendioMd": st.session_state.compendio_md,
                    "previous_context": "",
                    "capituloConstruir": chapter_id,
                    "mapeoContenido": json.dumps(mapeo_contenido)
                }
                
                stream_container = st.empty()
                result = process_wordware_api(APP_IDS["chapter_creator"], inputs, stream_container)
                
                status_placeholder.empty()
                
                if result:
                    generated_chapter = result.get('generatedChapter', {})
                    chapter_data = generated_chapter.get('chapterTitle', {})
                    
                    if chapter_data:
                        st.session_state.generated_chapters[chapter_id] = chapter_data.copy()
                        
                        if chapter_id not in st.session_state.chapters_completed:
                            st.session_state.chapters_completed.append(chapter_id)
                        
                        st.success(f"✅ {chapter_id} generado exitosamente!")
                        st.balloons()
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error("❌ Respuesta malformada del API")
                else:
                    st.error("❌ Fallo en la llamada al API")
        
        # --- CHAPTER REVIEW ---
        if chapter_exists:
            chapter_data = st.session_state.generated_chapters[chapter_id]
            
            with st.expander(f"📖 Ver Capítulo Generado", expanded=is_content_edit_mode):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.metric("Word Count", chapter_data.get('conteo_palabras', 'N/A'))
                
                with col2:
                    edit_button_label = "💾 Guardar Cambios" if is_content_edit_mode else "✏️ Editar Contenido"
                    if st.button(edit_button_label, key=f"edit_content_btn_{chapter_id}"):
                        if is_content_edit_mode:
                            edited_content = st.session_state.get(f"edit_content_{chapter_id}", "")
                            st.session_state.generated_chapters[chapter_id]['contenido_capitulo'] = edited_content
                            word_count = len(edited_content.split())
                            st.session_state.generated_chapters[chapter_id]['conteo_palabras'] = word_count
                            st.session_state.edit_modes[chapter_id] = False
                            st.success("✅ Cambios guardados!")
                            st.rerun()
                        else:
                            st.session_state.edit_modes[chapter_id] = True
                            st.rerun()
                
                with col3:
                    if st.button("🔄 Regenerar", key=f"regen_{chapter_id}"):
                        st.session_state.editing_params_for = chapter_id
                        st.rerun()
                
                st.markdown("#### Referencias Usadas")
                st.write(chapter_data.get('referencias_usadas', []))
                
                st.markdown("#### Contenido del Capítulo")
                if is_content_edit_mode:
                    st.text_area("Editar contenido:", value=chapter_data.get('contenido_capitulo', ''), height=400, key=f"edit_content_{chapter_id}")
                else:
                    st.markdown(chapter_data.get('contenido_capitulo', 'No content found.'))
        
        st.divider()
    
    if completed_chapters >= total_chapters:
        st.success("✅ Todos los capítulos generados. Procede a Stage 5.")

#---- Stage 5: Final Ebook Assembly ---
def render_stage_5():
    st.header("Stage 5: Final Ebook Assembly")
    st.markdown("This final stage will assemble all generated chapters, create a table of contents, and produce the complete ebook in Markdown format.")

    if not st.session_state.book_complete:
        st.warning("Please complete all chapter generations in Stage 4 before proceeding.")
        return

    if st.button("Assemble Final Ebook", type="primary"):
        st.session_state.stage_5_status = 'in_progress'
        
        all_chapters_content = "\n\n---\n\n".join(
            [ch.get('contenido_capitulo', '') for id, ch in sorted(st.session_state.generated_chapters.items())]
        )
        
        inputs = {
            "GeneratedEbook": all_chapters_content,
            "EsqueletoMaestro": json.dumps(st.session_state.skeleton.get('EsqueletoMaestro', {}))
        }

        st.info("Assembling the final ebook... This may take a moment.")
        stream_container = st.empty()
        result = process_wordware_api(APP_IDS["table_generator"], inputs, stream_container)

        if result:
            # Handle non-structured generation response
            if isinstance(result, dict):
                # Get the first string value from the dictionary
                for key, value in result.items():
                    if isinstance(value, str):
                        st.session_state.final_ebook = value
                        break
                else:
                    # If no string values found, convert entire dict to string
                    st.session_state.final_ebook = str(result)
            else:
                st.session_state.final_ebook = result
            
            st.session_state.stage_5_status = 'completed'
            st.success("🎉 Ebook Generation Complete! 🎉")
            st.balloons()
        else:
            st.session_state.stage_5_status = 'error'
            st.error("Failed to assemble the final ebook.")
        st.rerun()

    if st.session_state.stage_5_status == 'completed':
        st.success("✅ The final ebook has been generated successfully!")
        st.download_button(
            label="Download Final Ebook.md",
            data=st.session_state.final_ebook.encode('utf-8'),
            file_name="complete_ebook.md",
            mime="text/markdown",
            use_container_width=True
        )
        with st.expander("Preview Final Ebook", expanded=True):
            st.markdown(st.session_state.final_ebook)

# --- MAIN APPLICATION LOGIC ---

def main():
    # """Main function to run the Streamlit app."""
    st.title("E-Book - Inator V3.0")
    
    # Password protection - ADD THESE 3 LINES
    if not check_password():
        st.stop()
    
    # st.title("Wordware Ebook Generation Pipeline")
    st.markdown("Follow the stages in the sidebar to transform your source documents into a complete ebook.")

    initialize_session_state()
    render_sidebar()
    render_progress_indicator()

    # Main content area based on the current stage
    if st.session_state.current_stage == 1:
        render_stage_1()
    elif st.session_state.current_stage == 2:
        render_stage_2()
    elif st.session_state.current_stage == 3:
        render_stage_3()
    elif st.session_state.current_stage == 4:
        render_stage_4()
    elif st.session_state.current_stage == 5:
        render_stage_5()

if __name__ == "__main__":
    main()
