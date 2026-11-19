import os
import shutil


def process_project_tests(projects_list, target_root_dir, dataset, model, language, save_mode=True):
    """
    处理项目测试文件：可以选择备份并清空，或者直接删除。
    支持 Java (src/test/java 下的目录) 和 Python (tests 下的 .py 文件)。
    """

    # 1. 构建动态备份路径
    # 路径格式: target_root / dataset / model / language
    backup_base_dir = os.path.join(target_root_dir, dataset, model, language)

    action_name = "备份并移除" if save_mode else "直接删除"
    lang_display = language.upper()
    print(f"--- 开始处理 {lang_display} 项目测试源文件 [{action_name}] ---")

    if save_mode:
        print(f"备份目标根目录: {backup_base_dir}")
        os.makedirs(backup_base_dir, exist_ok=True)
    else:
        print("注意: save_mode=False，测试文件将被永久删除，不进行备份。")
    print("")

    for project_path in projects_list:
        project_name = os.path.basename(project_path.rstrip('/\\'))
        print(f"--- 正在处理项目: {project_name} ---")

        # 2. 根据语言定义源路径和筛选规则
        source_dir = ""
        items_to_process = []

        if language.lower() == 'java':
            # Java: src/test/java
            source_dir = os.path.join(project_path, 'src', 'test', 'java')
        elif language.lower() == 'python':
            # Python: tests
            source_dir = os.path.join(project_path, 'tests')
        else:
            print(f"  ❌ 错误: 不支持的语言 '{language}'")
            continue

        # 3. 检查源目录是否存在
        if not os.path.isdir(source_dir):
            print(f"  🟡 跳过: 源目录 '{source_dir}' 不存在。\n")
            continue

        # 4. 筛选要移动/删除的项目
        try:
            all_items = os.listdir(source_dir)
            if language.lower() == 'java':
                # Java: 筛选 文件夹 (packages)
                items_to_process = [i for i in all_items if os.path.isdir(os.path.join(source_dir, i))]
            elif language.lower() == 'python':
                # Python: 筛选 .py 文件
                items_to_process = [i for i in all_items if
                                    i.endswith('.py') and os.path.isfile(os.path.join(source_dir, i))]

            if not items_to_process:
                print(f"  - 源目录 '{os.path.basename(source_dir)}' 中没有符合条件的内容，无需处理。\n")
                continue
        except Exception as e:
            print(f"  ❌ 错误: 无法读取源目录 '{source_dir}': {e}\n")
            continue

        # 5. 如果是备份模式，准备目标文件夹
        destination_project_dir = None
        if save_mode:
            destination_project_dir = os.path.join(backup_base_dir, project_name)
            try:
                # 只有当备份目录存在且非空时才需要清理，或者直接创建
                # 注意：Python只是移动文件进去，Java是移动文件夹进去。
                # 为了保持纯净，建议每次都清理旧备份重建目录
                if os.path.exists(destination_project_dir):
                    print(f"  - 清理旧备份目录: {destination_project_dir}")
                    shutil.rmtree(destination_project_dir)
                os.makedirs(destination_project_dir)
            except Exception as e:
                print(f"  ❌ 错误: 无法创建备份目录 '{destination_project_dir}': {e}\n")
                continue

        # 6. 执行操作 (移动 或 删除)
        print(f"  - 找到 {len(items_to_process)} 个项目，准备执行: {action_name}...")
        success_count = 0

        for item_name in items_to_process:
            source_item_path = os.path.join(source_dir, item_name)
            try:
                if save_mode:
                    # --- 模式 A: 移动 (备份) ---
                    # 无论是文件(Python)还是文件夹(Java)，shutil.move 都能处理
                    # move 会把 source_item_path 移动到 destination_project_dir 里面
                    shutil.move(source_item_path, destination_project_dir)
                else:
                    # --- 模式 B: 删除 (不备份) ---
                    if os.path.isdir(source_item_path):
                        shutil.rmtree(source_item_path)  # 删除文件夹 (Java)
                    else:
                        os.remove(source_item_path)  # 删除文件 (Python)

                success_count += 1
            except Exception as e:
                print(f"    - 处理 '{item_name}' 失败: {e}")

        # 7. 打印结果
        if success_count == len(items_to_process):
            if save_mode:
                print(f"  ✅ 成功: 已将内容移动到 '{destination_project_dir}'")
            else:
                print(f"  🗑️ 成功: 已删除源目录下的内容")
        else:
            print(f"  ⚠️ 完成: {success_count}/{len(items_to_process)} 个项目处理成功。")
        print("")

    print("--- 所有项目处理完毕 ---")


if __name__ == '__main__':
    # ================= 配置区域 =================

    # 1. 基础参数
    DATASET_NAME = "deveval"
    MODEL_NAME = "deepseek-mate"
    TARGET_ROOT_PATH = '/home/mgh/dev/data/result'

    # 2. Save 开关 (True=移动备份, False=直接删除)
    SAVE_BACKUP = True

    # 3. 选择要运行的模式 (取消注释其中一块)

    # --- 模式 A: JAVA ---
    LANGUAGE = "java"
    PROJECT_DIRECTORIES = [
        # PT
        # '/home/mgh/dev/data/dataset/PT/JAVA/bankingApplication',
        # '/home/mgh/dev/data/dataset/PT/JAVA/CalculatorOOPS',
        # '/home/mgh/dev/data/dataset/PT/JAVA/libraryManagement',
        # '/home/mgh/dev/data/dataset/PT/JAVA/passwordGenerator',
        # '/home/mgh/dev/data/dataset/PT/JAVA/PongGame'

        # DevEval java
        '/home/mgh/dev/data/dataset/DevEval/java/Actor_relationship_game',
        # '/home/mgh/dev/data/dataset/DevEval/java/idcenter',
        # '/home/mgh/dev/data/dataset/DevEval/java/java_heap',
        # '/home/mgh/dev/data/dataset/DevEval/java/redis-cache'

        # ChatUniTest
        # '/home/mgh/dev/data/ChatUniTest/Actor_relationship_game'
    ]

    # --- 模式 B: PYTHON ---
    # LANGUAGE = "python"
    # PROJECT_DIRECTORIES = [
        # PT
        # '/home/mgh/dev/data/dataset/PT/Python/fuzzywuzzy',
        # '/home/mgh/dev/data/dataset/PT/Python/stock2',
        # '/home/mgh/dev/data/dataset/PT/Python/stock4',
        # '/home/mgh/dev/data/dataset/PT/Python/structly',
        # '/home/mgh/dev/data/dataset/PT/Python/tree'

        # DevEval
        # '/home/mgh/dev/data/dataset/DevEval/python/ArXiv_digest/ArXiv',
        # '/home/mgh/dev/data/dataset/DevEval/python/chakin/chakin_src',
        # '/home/mgh/dev/data/dataset/DevEval/python/geotext/geotext_src',
        # '/home/mgh/dev/data/dataset/DevEval/python/hone/hone_src',
        # '/home/mgh/dev/data/dataset/DevEval/python/lice/lice_src',
        # '/home/mgh/dev/data/dataset/DevEval/python/particle-swarm-optimization/pso',
        # '/home/mgh/dev/data/dataset/DevEval/python/readtime/src'


    # ]

    # ===========================================

    if 'path/to' in TARGET_ROOT_PATH:
        print("✋ 请先配置实际路径。")
    else:
        process_project_tests(
            projects_list=PROJECT_DIRECTORIES,
            target_root_dir=TARGET_ROOT_PATH,
            dataset=DATASET_NAME,
            model=MODEL_NAME,
            language=LANGUAGE,
            save_mode=SAVE_BACKUP
        )



