"""SysMoBench integration for System Intelligence Benchmark Suite."""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add paths
SDK_ROOT = Path(__file__).parent.parent.parent.parent
SYSMOBENCH_CORE = Path(__file__).parent.parent / "sysmobench_core"
sys.path.insert(0, str(SDK_ROOT))
sys.path.insert(0, str(SYSMOBENCH_CORE))

# Import SDK
from sdk.utils import set_llm_endpoint_from_config  # noqa: E402
set_llm_endpoint_from_config(str(Path(__file__).parent.parent / 'env.toml'))

# Import SysMoBench
from tla_eval.tasks.loader import TaskLoader  # noqa: E402
from tla_eval.methods import get_method  # noqa: E402
from tla_eval.models.base import GenerationResult  # noqa: E402
from tla_eval.evaluation.syntax.compilation_check import CompilationCheckEvaluator  # noqa: E402
from tla_eval.evaluation.semantics.runtime_coverage_evaluator import RuntimeCoverageEvaluator  # noqa: E402
from tla_eval.config import get_configured_model  # noqa: E402

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def run_evaluation(task, method, model_name, max_iterations=3):
    """Run iterative evaluation with correction."""
    logger.info(f"Evaluating {task.task_name} with max {max_iterations} iterations")

    # Initial generation
    start = time.time()
    gen_result = method.generate(task, model_name)
    if not gen_result.success:
        return {'success': False, 'error': gen_result.error_message, 'final_score': 0.0}

    current_spec = gen_result.tla_specification
    current_gen = gen_result

    # Evaluators
    comp_eval = CompilationCheckEvaluator(validation_timeout=60)
    runtime_eval = RuntimeCoverageEvaluator(num_simulations=100, simulation_depth=100, tlc_timeout=300)

    # Iteration loop
    for i in range(1, max_iterations + 1):
        logger.info(f"=== Iteration {i}/{max_iterations} ===")
        errors = []

        # Phase 1: Compilation
        comp_result = comp_eval.evaluate(current_gen, task.task_name, method.name, model_name, task.spec_module)
        comp_pass = comp_result.overall_success

        if comp_pass:
            logger.info(f"  ✓ Compilation PASS")
            # Phase 2: Runtime
            runtime_result = runtime_eval.evaluate(current_gen, task.task_name, method.name, model_name, task.spec_module)
            runtime_pass = runtime_result.overall_success

            if runtime_pass:
                logger.info(f"  ✓ Runtime PASS - SUCCESS at iteration {i}")
                return {
                    'success': True,
                    'iteration': i,
                    'total_time': time.time() - start,
                    'compilation': comp_result,
                    'runtime': runtime_result,
                    'final_score': 1.0
                }
            else:
                logger.info(f"  ✗ Runtime FAIL")
                errors.append(f"Runtime: {getattr(runtime_result, 'error_message', 'failed')}")
        else:
            logger.info(f"  ✗ Compilation FAIL")
            errors.extend([f"Compilation: {e}" for e in comp_result.syntax_errors + comp_result.semantic_errors])

        # Correction for next iteration
        if i < max_iterations and hasattr(method, '_generate_correction'):
            logger.info(f"  Generating correction... ({len(errors)} errors)")
            model_obj = get_configured_model(model_name)
            correction = method._generate_correction(task, current_spec, errors, model_obj)
            if correction.success:
                current_spec = correction.generated_text
                current_gen = GenerationResult(current_spec, correction.metadata, time.time(), True)
                logger.info(f"  ✓ Corrected for iteration {i+1}")

    # Failed all iterations
    logger.info(f"✗ FAILED after {max_iterations} iterations")
    comp_score = 0.5 if comp_result.overall_success else 0.0
    runtime_score = 0.5 if (comp_result.overall_success and runtime_result.overall_success) else 0.0

    return {
        'success': False,
        'total_time': time.time() - start,
        'compilation': comp_result,
        'runtime': runtime_result if comp_result.overall_success else None,
        'final_score': comp_score + runtime_score
    }


def main(input_file, output_dir, model_name, agent_name, max_iterations):
    """Main entry point."""
    # Change working directory to sysmobench_core so relative paths work correctly
    os.chdir(SYSMOBENCH_CORE)

    logger.info(f"SysMoBench | Model: {model_name} | Method: {agent_name} | Max iterations: {max_iterations}")

    # Initialize
    task_loader = TaskLoader(
        tasks_dir=str(SYSMOBENCH_CORE / "tla_eval" / "tasks"),
        cache_dir=str(SYSMOBENCH_CORE / "data" / "repositories")
    )
    method = get_method(agent_name)
    scores = []

    # Process tasks
    with open(input_file) as f, open(os.path.join(output_dir, 'result.jsonl'), 'w') as out:
        for line in f:
            item = json.loads(line)
            task_id, task_name = item['id'], item['task_name']
            logger.info(f"\n{'='*70}\nTask: {task_id} ({task_name})\n{'='*70}")

            try:
                task = task_loader.load_task(task_name)
                result = run_evaluation(task, method, model_name, max_iterations)

                output = {
                    'id': task_id,
                    'task_name': task_name,
                    'model_name': model_name,
                    'success': result['success'],
                    'final_score': result['final_score'],
                    'total_time': result.get('total_time', 0),
                    'iteration': result.get('iteration', max_iterations)
                }
                scores.append(result['final_score'])
            except Exception as e:
                logger.error(f"Error: {e}")
                output = {'id': task_id, 'error': str(e), 'final_score': 0.0}
                scores.append(0.0)

            out.write(json.dumps(output) + '\n')
            out.flush()

    # Save summary
    avg_score = {'final_score': sum(scores) / len(scores) if scores else 0.0, 'total_tasks': len(scores)}
    with open(os.path.join(output_dir, 'avg_score.json'), 'w') as f:
        json.dump(avg_score, f, indent=2)

    logger.info(f"\n{'='*70}\nFinal Score: {avg_score['final_score']:.3f}\n{'='*70}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SysMoBench Evaluation')
    parser.add_argument('-i', '--input_file', default='./data/benchmark/tasks.jsonl')
    parser.add_argument('-o', '--save_path', default=None)
    parser.add_argument('-a', '--agent', default='agent_based')
    parser.add_argument('-m', '--model_name', required=True)
    parser.add_argument('--max_iterations', type=int, default=3)
    args = parser.parse_args()

    # Output directory
    if not args.save_path:
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        args.save_path = f"./outputs/sysmobench__{args.model_name.replace('/', '_')}__{args.agent}__{timestamp}"

    # Convert to absolute paths before changing working directory
    input_file = str(Path(args.input_file).resolve())
    save_path = str(Path(args.save_path).resolve())
    os.makedirs(save_path, exist_ok=True)

    main(input_file, save_path, args.model_name, args.agent, args.max_iterations)
