import type { ForcePostStepRecord, ForcePostStepStatus } from '../lib/forcePostSteps';
import { formatDuration, formatPipelineError, splitStepErrorLabel, stepDurationMs } from '../lib/forcePostSteps';

type ForcePostTrackerProps = {
  steps: ForcePostStepRecord[];
  now: number;
};

function StepIcon({ status }: { status: ForcePostStepStatus }) {
  if (status === 'active') {
    return <span className="force-post-tracker__icon force-post-tracker__icon--spin" aria-hidden="true" />;
  }
  if (status === 'done') {
    return (
      <span className="force-post-tracker__icon force-post-tracker__icon--done" aria-hidden="true">
        ✓
      </span>
    );
  }
  if (status === 'error') {
    return (
      <span className="force-post-tracker__icon force-post-tracker__icon--error" aria-hidden="true">
        ✕
      </span>
    );
  }
  return <span className="force-post-tracker__icon force-post-tracker__icon--pending" aria-hidden="true" />;
}

export function ForcePostTracker({ steps, now }: ForcePostTrackerProps) {
  return (
    <ol className="force-post-tracker" aria-label="Force post pipeline progress">
      {steps.map((step) => {
        const { status } = step;
        const { title, detail } =
          status === 'error' ? splitStepErrorLabel(step.label) : { title: step.label, detail: null };
        const errorDetail = detail ? formatPipelineError(detail) : null;
        const duration = formatDuration(stepDurationMs(step, now));
        return (
          <li
            key={step.stepId}
            className={`force-post-tracker__step force-post-tracker__step--${status}`}
          >
            <StepIcon status={status} />
            <div className="force-post-tracker__text">
              <span className="force-post-tracker__label">{title}</span>
              {status === 'error' && errorDetail ? (
                <span className="force-post-tracker__error-detail" role="alert">
                  {errorDetail}
                </span>
              ) : null}
            </div>
            {duration ? <span className="force-post-tracker__duration">{duration}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}
