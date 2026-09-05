from enum import Enum

class State(Enum):
    IDEA = "IDEA"
    RESEARCH = "RESEARCH"
    FACT_CHECK = "FACT_CHECK"
    CREATIVE_DIRECTION = "CREATIVE_DIRECTION"
    SCRIPT = "SCRIPT"
    SCENE_PLANNING = "SCENE_PLANNING"
    ASSET_GENERATION = "ASSET_GENERATION"
    VOICE = "VOICE"
    AUDIO = "AUDIO"
    EDITING = "EDITING"
    CAPTIONS = "CAPTIONS"
    THUMBNAIL = "THUMBNAIL"
    METADATA = "METADATA"
    POLICY_CHECK = "POLICY_CHECK"
    FINAL_QC = "FINAL_QC"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    APPROVED = "APPROVED"
    GDRIVE_DELIVERY = "GDRIVE_DELIVERY"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"

def get_next_tasks(current_state):
    transitions = {
        State.IDEA: [State.RESEARCH],
        State.RESEARCH: [State.FACT_CHECK],
        State.FACT_CHECK: [State.CREATIVE_DIRECTION],
        State.CREATIVE_DIRECTION: [State.SCRIPT],
        State.SCRIPT: [State.SCENE_PLANNING],
        State.SCENE_PLANNING: [State.ASSET_GENERATION],
        State.ASSET_GENERATION: [State.VOICE],
        State.VOICE: [State.AUDIO],
        State.AUDIO: [State.EDITING],
        State.EDITING: [State.CAPTIONS],
        State.CAPTIONS: [State.THUMBNAIL],
        State.THUMBNAIL: [State.METADATA],
        State.METADATA: [State.POLICY_CHECK],
        State.POLICY_CHECK: [State.FINAL_QC, State.BLOCKED],
        State.FINAL_QC: [State.HUMAN_REVIEW],
        State.HUMAN_REVIEW: [State.APPROVED],
        State.APPROVED: [State.GDRIVE_DELIVERY],
        State.GDRIVE_DELIVERY: [State.DELIVERED],
    }
    return transitions.get(current_state, [State.FAILED])