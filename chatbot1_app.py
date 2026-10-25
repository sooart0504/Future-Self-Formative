"""
chatbot1_app.py
Future Self Formative Study — Chatbot 1: Ideal Future Self + Anchoring Statements

State machine:
  start → anchoring → gen_stories → pick_persona
        → rate_story → [revise_story] → complete

URL params:
  ?pid=FSS_001
"""

import os
import sys
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate
from langchain_classic.chains import ConversationChain
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers.json import SimpleJsonOutputParser
from langsmith import Client, traceable
import streamlit as st
import streamlit.components.v1 as components

from llm_config import LLMConfig


# ── Environment ───────────────────────────────────────────────────────────────
os.environ["OPENAI_API_KEY"]       = st.secrets["OPENAI_API_KEY"]
os.environ["OPENAI_API_BASE"] = st.secrets["OPENAI_API_BASE"]
os.environ["LANGCHAIN_API_KEY"]    = st.secrets["LANGCHAIN_API_KEY"]
os.environ["LANGCHAIN_PROJECT"]    = st.secrets["LANGCHAIN_PROJECT"]
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# ── Config ────────────────────────────────────────────────────────────────────
input_args  = sys.argv[1:]
config_file = input_args[0] if input_args else st.secrets.get("CONFIG_FILE_CB1", "chatbot1_config.toml")
cfg = LLMConfig(config_file)

participant_id = st.query_params.get("pid", "unknown")
smith_client   = Client()

st.set_page_config(page_title="Future Self — Part 1", page_icon="🌱")
st.markdown("<style>[data-testid='stToolbarActions']{visibility:hidden;}</style>", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
defaults = {
    "agentState":          "start",
    "consent":             False,
    "created_time":        datetime.now(),
    "answers_t1":          {},
    "timeline_horizon":    "",   # locked FSCQ horizon, e.g. "in 2 years"
    "horizon_framing":     "",   # "duration" or "retirement"
    "anchoring_responses": {},   # {field_name: response_text}
    "topic1_stories":      [],
    "locked_persona":      None,
    "locked_persona_name": None,
    "story_final":         None,
    "revision_history":    [],
    "revision_count":      0,
    "llm_model":           "gpt-4o",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Per-topic message histories ───────────────────────────────────────────────
msgs_t1   = StreamlitChatMessageHistory(key="msgs_topic1")
memory_t1 = ConversationBufferMemory(memory_key="history", chat_memory=msgs_t1)


# ── Google Sheets ─────────────────────────────────────────────────────────────
SHEET_KEY = st.secrets.get("GOOGLE_SHEET_KEY", "YOUR_SHEET_KEY_HERE")

def save_to_sheet():
    """Saves all Chatbot 1 outputs to Tab 1 (worksheet index 0) of the study sheet.

    The row is assembled by matching the sheet's OWN header row by name,
    not by counting positions. This matters: the earlier version built a
    fixed-length list and appended it, so inserting or reordering a single
    column in the sheet silently shifted every value after it into the
    wrong column, with no error and no way to tell from the data.

    Writing by name means column order in the sheet no longer has to agree
    with any order in this file. Adding a field is a one-line change here
    plus a new heading in the sheet, in whatever position reads best.
    """
    creds  = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sheet  = client.open_by_key(SHEET_KEY).get_worksheet(0)

    t1      = st.session_state.get("answers_t1", {})
    anchors = st.session_state.get("anchoring_responses", {})

    # Every value this chatbot produces, keyed by its column heading.
    values = {
        "PID":                      participant_id,
        "timestamp_start":          str(st.session_state.get("created_time", "")),
        "timestamp_end":            str(datetime.now()),
        "persona_selected":         str(st.session_state.get("locked_persona_name", "")),

        # Topic 1 extracted answers
        "values":                   str(t1.get("values", "")),
        "full_life":                str(t1.get("full_life", "")),
        "health_foundation":        str(t1.get("health_foundation", "")),
        "future_self_description":  str(t1.get("future_self_description", "")),
        "timeline":                 str(t1.get("timeline", "")),

        # Final narrative
        "narrative_ideal":          str(st.session_state.get("story_final", "")),

        # The locked FSCQ horizon, e.g. "in 2 years". Reused verbatim by the
        # check-in page and every later administration.
        "timeline_horizon":         str(st.session_state.get("timeline_horizon", "")),

        "revision_count":           str(st.session_state.get("revision_count", 0)),
        "chat_log_t1":              str(msgs_t1.messages),
    }

    # Anchoring statements — field names come from chatbot1_config.toml,
    # so adding a prompt there needs no change here.
    for field in cfg.anchoring_fields:
        values[field] = str(anchors.get(field, ""))

    headers = [str(h).strip() for h in sheet.row_values(1)]

    # horizon_framing is metadata — whether they reached their horizon
    # directly or via the retirement route. Deliberately best-effort: it is
    # added ONLY if the column exists, because the strict check below aborts
    # the whole save on an unmatched field, and losing an entire session over
    # an optional flag would be a far worse failure than losing the flag.
    if "horizon_framing" in headers:
        values["horizon_framing"] = str(st.session_state.get("horizon_framing", ""))

    if not headers:
        raise RuntimeError(
            "Tab 1 of the study sheet has no header row. The row cannot be "
            "written by column name until the headings exist."
        )

    # A value with no matching heading would otherwise vanish without a
    # trace — the one real risk of writing by name. Catch it loudly here
    # rather than discovering missing anchors during analysis.
    unmatched = [k for k in values if k not in headers]
    if unmatched:
        raise RuntimeError(
            "These fields have no matching column heading in Tab 1 of the "
            "study sheet: " + ", ".join(sorted(unmatched)) +
            ". Add the heading(s) to the sheet — spelling and capitals must "
            "match exactly — then try again. Nothing was saved."
        )

    row = [values.get(h, "") for h in headers]
    sheet.append_row(row)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_llm(temperature=0.3):
    return ChatOpenAI(
        temperature=temperature,
        model=st.session_state.llm_model,
        openai_api_key=st.secrets["OPENAI_API_KEY"],
        openai_api_base=st.secrets["OPENAI_API_BASE"]
    )


def extract_answers(msgs, keys, extraction_template):
    """Extracts structured answers from a conversation."""
    template    = PromptTemplate(input_variables=["conversation_history"], template=extraction_template)
    chain       = template | get_llm(0.1) | SimpleJsonOutputParser()
    return chain.invoke({"conversation_history": msgs})


# ── Topic conversation runner ─────────────────────────────────────────────────
def run_topic_conversation(topic_num, msgs, memory, prompt_template, container):
    """
    Runs the Q&A conversation for a topic.
    Returns True when FINISHED, False if still ongoing.
    """
    if len(msgs.messages) == 0:
        intro_text = cfg.intro if topic_num == 1 else getattr(cfg, f"topic{topic_num}_transition")
        msgs.add_ai_message(intro_text)

    # Show last AI message
    if msgs.messages and msgs.messages[-1].type == "ai":
        with container:
            st.chat_message("ai").write(msgs.messages[-1].content)

    if prompt:
        prompt_obj   = PromptTemplate(input_variables=["history", "input"], template=prompt_template)
        conversation = ConversationChain(prompt=prompt_obj, llm=get_llm(0.3), verbose=False, memory=memory)

        with container:
            st.chat_message("human").write(prompt)
            response = conversation.invoke(input=prompt)

            if "FINISHED" in response["response"]:
                st.divider()
                st.chat_message("ai").write(cfg.questions_outro)
                return True
            else:
                st.chat_message("ai").write(response["response"])

    return False


# ── Story generation ──────────────────────────────────────────────────────────
@traceable
def generate_stories():
    """
    Extracts answers from topic 1, generates 3 persona stories,
    stores them in session state, transitions to pick_persona.
    """
    st.session_state["answers_t1"] = extract_answers(
        msgs_t1.messages, cfg.topic1_keys, cfg.topic1_extraction_template)

    t1_answers  = st.session_state["answers_t1"]
    all_answers = {k: t1_answers.get(k, "") for k in cfg.topic1_keys}

    prompt_obj  = PromptTemplate.from_template(cfg.story_prompt_template)
    json_parser = SimpleJsonOutputParser()
    chain       = prompt_obj | get_llm(0.7) | json_parser

    progress = st.progress(0, "Generating your stories...")
    stories  = []

    for i, persona in enumerate(cfg.personas):
        result = chain.invoke({
            "persona":    persona,
            "one_shot":   cfg.one_shot,
            "end_prompt": (
                "Create an ideal future self micro-narrative based on the information above. "
                "The narrative MUST do all of the following:\n"
                "1. Open by grounding the story in 1–2 of this person's core values, "
                "using their own words or close paraphrases — make the values feel specific to them, not generic.\n"
                "2. Show explicitly how being physically active and healthy ENABLES this person to live in "
                "alignment with those values — not as a separate health goal, but as the physical foundation "
                "that makes their valued life possible. This connection must be unmistakable.\n"
                "3. Paint a vivid, specific scene of this person as their future self — active, energized, "
                "and living the life they described — in a moment that captures how physical vitality and "
                "personal values are intertwined.\n"
                "The tone, length, and voice should match the persona you have been given."
            )
        } | all_answers)
        stories.append(result.get("output_scenario", ""))
        progress.progress(int((i + 1) / 3 * 100), "Generating your stories...")

    st.session_state["topic1_stories"] = stories
    st.session_state["agentState"]     = "pick_persona"
    st.rerun()


def show_persona_picker():
    """Shows 3 story options for participant to choose from."""
    stories = st.session_state.get("topic1_stories", [])

    st.chat_message("ai").write(
        "Here are three versions of your future self story. "
        "Each one is based on what you shared — just written in a different voice. "
        "Take a moment to read them and choose the one that resonates most with you."
    )
    st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Version 1")
        st.write(stories[0] if len(stories) > 0 else "")
        if st.button("Choose Version 1", key="pick1"):
            lock_persona(0, stories[0])

    with col2:
        st.subheader("Version 2")
        st.write(stories[1] if len(stories) > 1 else "")
        if st.button("Choose Version 2", key="pick2"):
            lock_persona(1, stories[1])

    with col3:
        st.subheader("Version 3")
        st.write(stories[2] if len(stories) > 2 else "")
        if st.button("Choose Version 3", key="pick3"):
            lock_persona(2, stories[2])


def lock_persona(index, story):
    """Saves chosen story and persona, transitions to rate_story."""
    st.session_state["locked_persona"]      = cfg.personas[index]
    st.session_state["locked_persona_name"] = cfg.persona_names[index]
    st.session_state["story_final"]         = story
    st.session_state["agentState"]          = "rate_story"
    st.rerun()


# ── Story review + anchoring display ─────────────────────────────────────────
def show_rate_story():
    """
    Shows the chosen story for review.
    Anchoring statements are displayed below it, read-only.
    """
    st.chat_message("ai").write(
        "Here is your story. Read it through and let us know how it feels."
    )
    st.markdown(f"> {st.session_state['story_final']}")
    st.divider()

    # Show anchoring statements (read-only, for review)
    anchors = st.session_state.get("anchoring_responses", {})
    if anchors:
        st.chat_message("ai").write(
            "And here are the statements you completed — these are the words of your future self:"
        )
        for field, prompt_text in zip(cfg.anchoring_fields, cfg.anchoring_prompts):
            response = anchors.get(field, "")
            st.markdown(f"**{prompt_text}…** {response}")
        st.divider()

    st.chat_message("ai").write("How well does this story capture what you had in mind?")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Needs some edits", key="rate_edits"):
            st.session_state["agentState"] = "revise_story"
            st.rerun()
    with col2:
        if st.button("Pretty good, I'd like to tweak it", key="rate_tweak"):
            st.session_state["agentState"] = "revise_story"
            st.rerun()
    with col3:
        if st.button("This captures it perfectly!", key="rate_good"):
            st.session_state["agentState"] = "complete"
            st.rerun()


# ── Revision loop ─────────────────────────────────────────────────────────────
def show_revise_story():
    """Revision loop — story only, max 2 rounds."""

    revision_count = st.session_state.get("revision_count", 0)

    st.chat_message("ai").write("Here is your current story:")
    st.markdown(f"> {st.session_state['story_final']}")
    st.divider()

    if revision_count >= 2:
        st.chat_message("ai").write(
            "You've made two rounds of revisions — that's the maximum. "
            "Here is your final story! You can continue when you're ready."
        )
        if st.button("Continue", key="continue_after_revisions"):
            st.session_state["agentState"] = "complete"
            st.rerun()
        return

    st.chat_message("ai").write(
        "What would you like to change? You can type a request below, or edit the story directly."
    )

    # Option A: typed request
    user_request = st.text_input(
        "Type your request (e.g. 'Make it feel more hopeful')",
        key=f"revision_input_{revision_count}"
    )
    if st.button("Apply my request", key=f"apply_revision_{revision_count}") and user_request:
        prompt_obj  = PromptTemplate(
            input_variables=["input", "scenario"],
            template=cfg.adaptation_prompt_template
        )
        chain = prompt_obj | get_llm(0.5) | SimpleJsonOutputParser()

        with st.spinner("Revising your story..."):
            result = chain.invoke({
                "scenario": st.session_state["story_final"],
                "input":    user_request
            })

        new_story = result.get("new_scenario", st.session_state["story_final"])
        st.session_state["revision_history"].append({
            "round":     revision_count + 1,
            "request":   user_request,
            "new_story": new_story
        })
        st.session_state["story_final"]    = new_story
        st.session_state["revision_count"] += 1
        st.session_state["agentState"]     = "rate_story"
        st.rerun()

    st.divider()

    # Option B: direct edit
    st.write("Or edit the story directly:")
    edited = st.text_area(
        "Edit below:",
        value=st.session_state["story_final"],
        key=f"direct_edit_{revision_count}",
        height=200
    )
    if st.button("Save my edits", key=f"save_direct_{revision_count}"):
        st.session_state["revision_history"].append({
            "round":     revision_count + 1,
            "request":   "Direct edit by participant",
            "new_story": edited
        })
        st.session_state["story_final"]    = edited
        st.session_state["revision_count"] += 1
        st.session_state["agentState"]     = "complete"
        st.rerun()


# ── Timeline horizon ──────────────────────────────────────────────────────────
def show_horizon_picker():
    """
    Asks once, between the Topic 1 conversation and the anchoring form, how
    far away the participant's future self feels.

    The answer is stored as a full prepositional phrase ("in 2 years") and
    reused verbatim in every later FSCQ stem — the weekly 3-item measure
    during the trial and the full instrument at each endpoint. It is a fixed
    choice rather than free text because the stem has to read identically
    every time: "2 years" post-chatbot and "5 years" at endpoint would
    confound within-person change with horizon drift.

    No option is pre-selected. A default would be silently accepted by
    anyone clicking through, and this value cannot be recovered afterwards.

    One option — "Around when I retire" — carries no duration of its own, so
    choosing it reveals a follow-up asking for the number of years. What gets
    stored is still a duration either way; `horizon_framing` records which
    route they took.
    """
    # This is the ONLY place the duration is asked. The Topic 1 conversation
    # used to ask it too and now asks only what the future self is anchored
    # to, so there is nothing to reflect back here and no risk of a
    # conversational answer disagreeing with the stored choice.
    st.chat_message("ai").write(cfg.horizon_question)
    st.divider()

    labels = [opt["label"] for opt in cfg.horizon_options]

    choice = st.radio(
        label=cfg.horizon_helper or "Choose one",
        options=labels,
        index=None,                 # nothing pre-selected on purpose
        key="horizon_choice"
    )

    chosen = next((o for o in cfg.horizon_options if o["label"] == choice), None)
    needs_years = bool(chosen and chosen.get("ask_years"))

    # The follow-up appears inline, as soon as the retirement option is
    # picked, rather than on a second screen — it is one question and a
    # screen change would make it feel like a penalty for that answer.
    years_choice = None
    if needs_years:
        st.divider()
        st.markdown("**" + cfg.horizon_followup + "**")
        years_choice = st.radio(
            label=cfg.horizon_followup_helper or "Choose one",
            options=[o["label"] for o in cfg.horizon_options if o.get("stored")],
            index=None,
            key="horizon_years"
        )

    if st.button("Continue", key="submit_horizon"):
        if chosen is None:
            st.warning("Please choose one before continuing.")
            return

        if needs_years:
            if years_choice is None:
                st.warning("Please choose roughly how many years before continuing.")
                return
            stored  = next(o["stored"] for o in cfg.horizon_options
                           if o.get("stored") and o["label"] == years_choice)
            framing = "retirement"
        else:
            stored  = chosen["stored"]
            framing = "duration"

        st.session_state["timeline_horizon"] = stored
        st.session_state["horizon_framing"]  = framing
        st.session_state["agentState"]       = "anchoring"
        st.rerun()


# ── Anchoring form ────────────────────────────────────────────────────────────
def show_anchoring_form():
    """
    Sentence-completion form for the 8 anchoring statements.
    Collected before story generation.
    """
    st.chat_message("ai").write(
        "You've painted a meaningful picture of who you want to become. "
        "Now let's give that future self a voice.\n\n"
        "For a moment, imagine you already ARE this future self — not describing them from the outside, "
        "but actually being them, in their body, living their life. From inside that experience, "
        "complete each of the following sentences as if you are answering right now, as that person. "
        "There are no right answers — just write what feels true for them."
    )
    st.divider()

    responses = {}
    for field, prompt_text in zip(cfg.anchoring_fields, cfg.anchoring_prompts):
        val = st.text_input(
            label=f"{prompt_text}…",
            key=f"anchor_{field}",
            placeholder="Type your answer here"
        )
        responses[field] = val

    if st.button("Submit and see my story", key="submit_anchoring"):
        if all(responses[f].strip() for f in cfg.anchoring_fields):
            st.session_state["anchoring_responses"] = responses
            st.session_state["agentState"]          = "gen_stories"
            st.rerun()
        else:
            st.warning("Please complete all sentences before continuing.")


# ── Completion ────────────────────────────────────────────────────────────────
def complete_session():
    """Saves to Google Sheets and shows completion message."""
    with st.spinner("Saving your responses..."):
        save_to_sheet()

    st.success("All done — thank you!")
    st.markdown(
        "Your story and responses have been saved. "
        "You can now close this tab and return to the session."
    )
    components.html('<script>setTimeout(function(){ window.close(); }, 4000);</script>')


# ── State machine ─────────────────────────────────────────────────────────────
def state_agent():
    state = st.session_state["agentState"]

    if state == "start":
        finished = run_topic_conversation(
            1, msgs_t1, memory_t1,
            cfg.topic1_prompt_template,
            entry_container
        )
        if finished:
            # The horizon question comes first: it belongs with the future
            # self they have just finished describing, while that is still
            # in mind, and before the anchoring form shifts attention to
            # specific obstacle days.
            st.session_state["agentState"] = "horizon" if cfg.has_horizon else "anchoring"
            st.rerun()

    elif state == "horizon":
        show_horizon_picker()

    elif state == "anchoring":
        show_anchoring_form()

    elif state == "gen_stories":
        with st.spinner("Creating your stories — this takes about 30 seconds..."):
            generate_stories()

    elif state == "pick_persona":
        show_persona_picker()

    elif state == "rate_story":
        show_rate_story()

    elif state == "revise_story":
        show_revise_story()

    elif state == "complete":
        complete_session()


# ── Consent gate ──────────────────────────────────────────────────────────────
def mark_consent():
    st.session_state["consent"] = True


if st.session_state["consent"]:
    entry_container = st.expander("Our conversation", expanded=True)
    prompt = st.chat_input()

    if not st.secrets.get("OPENAI_API_KEY"):
        openai_key = st.sidebar.text_input("OpenAI API Key", type="password")
        if not openai_key:
            st.info("Enter an OpenAI API Key to continue.")
            st.stop()

    state_agent()

else:
    with st.container():
        st.markdown(cfg.intro_and_consent)
        st.button("I understand — let's begin", key="consent_btn", on_click=mark_consent)
