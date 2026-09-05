import logging
from app.state_machine import State, get_next_tasks
from app.tools import *
from database.db import get_job, update_job_state, log_error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Hermes")


class HermesAgent:
    def __init__(self, job_id):
        self.job_id = job_id

    async def run(self):
        job = await get_job(self.job_id)
        if not job: return
        self.state = State(job['state'])

        while self.state not in [State.DELIVERED, State.FAILED, State.BLOCKED]:
            next_states = get_next_tasks(self.state)
            for target in next_states:
                if target == State.BLOCKED:
                    await update_job_state(self.job_id, State.BLOCKED.value)
                    return
                try:
                    logger.info(f"➡️ Executing: {target.value}")

                    if target == State.RESEARCH: await research_tool(self.job_id)
                    elif target == State.FACT_CHECK: await fact_check_tool(self.job_id)
                    elif target == State.CREATIVE_DIRECTION: await creative_direction(self.job_id)
                    elif target == State.SCRIPT: await generate_script(self.job_id)
                    elif target == State.SCENE_PLANNING: await plan_scenes(self.job_id)
                    elif target == State.ASSET_GENERATION: await generate_assets(self.job_id)
                    elif target == State.VOICE: await generate_voice(self.job_id)
                    elif target == State.AUDIO: await mix_audio(self.job_id)
                    elif target == State.EDITING: await edit_video(self.job_id)
                    elif target == State.CAPTIONS: await add_captions(self.job_id)
                    elif target == State.THUMBNAIL: await generate_thumbnail(self.job_id)
                    elif target == State.METADATA: await generate_metadata(self.job_id)
                    elif target == State.POLICY_CHECK:
                        if not await policy_check(self.job_id):
                            self.state = State.BLOCKED
                            await update_job_state(self.job_id, State.BLOCKED.value)
                            return
                    elif target == State.FINAL_QC:
                        score = await run_qc(self.job_id)
                        # FIXED: threshold now comes from config.yaml instead of a
                        # hardcoded 85 duplicated here.
                        threshold = CONFIG.get("system", {}).get("quality_threshold", 85)
                        if score < threshold:
                            raise Exception(f"QC Failed: {score} < {threshold}")
                    elif target == State.HUMAN_REVIEW:
                        # FIXED: this used to fall through the if/elif chain doing
                        # nothing, so the pipeline sailed straight through to
                        # APPROVED with zero actual human gate. It now genuinely
                        # stops here — call POST /job/{job_id}/approve (or
                        # /reject) to move it forward.
                        self.state = target
                        await update_job_state(self.job_id, self.state.value)
                        logger.info(f"⏸️  Job {self.job_id} is waiting for human review.")
                        return
                    elif target == State.GDRIVE_DELIVERY:
                        await deliver_to_gdrive(self.job_id)

                    self.state = target
                    await update_job_state(self.job_id, self.state.value)
                    break
                except Exception as e:
                    logger.error(f"❌ Failed {target}: {e}")
                    await log_error(self.job_id, str(e))
                    self.state = State.FAILED
                    await update_job_state(self.job_id, State.FAILED.value)
                    return
