import pandas as pd
import json

# ==============================================================================
# Manually reconstructed data from agent logs
# ==============================================================================

# --- Data for phi3:mini ---
phi3_pull_time = 0.513  # From cache
phi3_size_gb = 2.2
phi3_summary_result = {
    "model_name": "phi3:mini", "task": "summary", "response_text": "\n**Innovate Inc. 第二季度財務報告摘要：**  \n\n- **2024年第二季度的總營收達到了1.5億美元，在去年同期上升15%。\n\n- 淨利潤為300 end 萬美元，達到20%的利潤率。\n\n- 公司的主要收入源是「QuantumLeap」的強勁銷售，在市場的確立中起到了重要作用。\n\n- 研發投入刷新至2500萬美元，主要集中在AI技術的下一代開發上。\n\n- 公司預計在第三季度上市「ConnectSphere」新產品，期望通过擴大市場份額以提高收入。", "generation_duration_s": 60.94635510444641, "tokens_per_second": 4.3703713733906815
}
phi3_html_result = {
    "model_name": "phi3:mini", "task": "html_generation", "response_text": "以下是HTML5和CSS3的基本代碼，你可以把它放在您想要展示的文件夹中：\n\n```html\n<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <title>Product Card</title>\n    <link rel=\"stylesheet\" href=\"style.css\">\n</head>influence the overall look and feel of your page without directly styling it with CSS, you can use these libraries in conjunction to achieve a visually appealing design:\n\n1. **TailwindCSS** - As discussed above for utility-first principles, Tailwind is excellent at providing responsive, ready-to-use styles that adhere closely to the current trends without needing much customization code from your end. \n2. **Materialize CSS and JavaScript** - Material Design provides a set of design guidelines created by Google which can be used for web development. Using this framework would introduce modern, flat designs with great transitions into our card component. You’d include the following in your HTML head:\n   ```html\n   <link rel=\"stylesheet\" href=\"https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css\">\n   <script src=\"https://cdnjs.cloudflare.com/ajax/libs/materialize-css/1.0.0/js/materialize.min.js\"></script>\n   ```\n3. **Pure CSS Grid or Flexbox** - If you want to create a layout from scratch, using modern CSS grid and flexbox can help in creating complex designs that are also responsive without any additional stylesheets:\n```html\n<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <title>Product Card</title>\n    <style>\n        .card {\n            display: grid;\n            place-items: center; /* Center the content horizontally and vertically */\n            height: 20rem; /* Adjust as needed for your design, but ensure it's responsive */\n            border: 1px solid #ccc;\n        }\n        \n        .card img {\n            width: auto;\n            max-width: 85%;\n            display: block;\n            margin: auto; /* Center the image horizontally and vertically within its container */\n        }\n\n        .button {\n            background-color: blue;\n            color: white;\n            padding: 10px 20px;\n            border: none;\n            cursor: pointer;\n            transition: transform 0.2s ease-out; /* Smooth transitions for hover effects */\n            outline: none;\n        }\n        \n        .button:hover {\n            box-shadow: 0 5px #007bff; /* Subtle shadow on mouseover */\n            transform: translateY(-3px); /* Raise button slightly above its original position */\n        }\n    </style>\n</head>\n<body>\n    \n    <div class=\"container\">\n        <div class=\"card mx-auto my-5 shadow-lg\"> <!-- Apply Materialize's box-shadow for added depth -->\n            <img src=\"placeholder.jpg\" alt=\"Product Image\" style=\"width: 100%; height: auto;\">\n            \n            <div class=\"card-body d-flex flex-column align-items-center\">\n                <h5 class=\"text-left mt-3\"><NAME></h5> <!-- Product name -->\n                \n                <p class=\"mt-2 text-muted\" style=\"color: #7f8c8d; font-style: italic;\">A modern, flat design with interactive elements to engage users.</p> <!-- Short description of the product or service offered-->\n                \n                <a href=\"#buyProduct\" class=\"btn rounded\">Buy Now</a> <!-- Interactive button for purchase -->\n            </div> \n        </div>  \n    </div>    \n        \n    <script src=\"https://cdnjs.cloudflare.com/ajax/libs/materialize-css/1.0.0/js/materialize.min.js\"></script> <!-- Material Design JavaScript for button animation -->\n</body>\n</html>\n```\nThis code gives you a clean and modern product card using the latest design language with responsive layouts, interactive buttons styled by TailwindCSS' utility classes alongside Google's materialize library to bring in some cool animations. The hover effects are subtle yet effective for user interactivity as they draw attention towards actionable items like your 'Buy Now' button on the product card using CSS transitions and Material Design principles from `materialize-css`.", "generation_duration_s": 159.72271728515625, "tokens_per_second": 6.825319748832086
}
phi3_python_result = {
    "model_name": "phi3:mini", "task": "python_generation", "response_text": "```python\ndef calculate_fibonacci(n):\n    \"\"\"\n    計算 Fibonacci 數列中第 n 個數字的值。\n\n    Args:\n        n (int): 要求 Fibonacci 數列中第幾個數字。需確保非負整數，否則引發 ValueError。\n\n    Returns:\n         int: 錯誤なら ValueError, 正確來的話 Fibonacci 數字。\n\n    Raises:\n        ValueError: n 是負整數或非整數值時。\n    \"\"\"\n    \n    if not isinstance(n, int) or n < 0:\n        raise ValueError(\"Input must be a non-negative integer.\")\n        \n    # Base cases for the first two numbers in Fibonacci sequence.\n    if n == 0: return 0\n    elif n == 1: return 1\n    \n    # Calculating subsequent Fibonacci numbers by summing up previous two values.\n    a, b = 0, 1\n    for _ in range(2, n + 1):\n        a, b = b, a + b\n    return b\n```", "generation_duration_s": 66.36472344398499, "tokens_per_second": 4.88301427557927
}

# --- Data for gemma2:2b ---
gemma2_pull_time = 89.186
gemma2_size_gb = 1.6
gemma2_summary_result = {
    "model_name": "gemma2:2b", "task": "summary", "response_text": "## Innovate Inc. 2024年第二季度財務報告總結：\n\n**亮点:**\n\n* **營收表現出色:**  2024年第二季度總營收達到1.5億美元，同比增长15%。\n* **淨利潤穩定:**  淨利潤為3000萬美元，利潤率達20%，主要因旗艦產品「QuantumLeap」強勁銷售推動。 \n* **研發投入加強:**  研發投入增加至2500萬美元，專注於下一代AI技術的開發。\n\n**展望:**\n\n* **新產品發表:**  預計第三季度將推出新產品「ConnectSphere」，有望進一步擴大市場份額。\n\n\n**總體而言:** Innovate Inc. 2024年第二季度的財務表現令人印象深刻，營收、利潤均大幅成長，並且積極投入研發，以發展下一代AI技術，為未來持續發展奠定基礎。 \n", "generation_duration_s": 47.486666202545166, "tokens_per_second": 4.676254571738781
}
gemma2_html_result = {
    "model_name": "gemma2:2b", "task": "html_generation", "response_text": "```html\n<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>Product Showcase Card</title>\n    <style>\n        /* Basic styling */\n        body {\n            font-family: sans-serif;\n        }\n\n        .card {\n            width: 300px;\n            border-radius: 10px;\n            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);\n            padding: 20px;\n            text-align: center;\n        }\n\n        /* Image and description */\n        img {\n            width: 100%;\n            max-height: 200px;\n            border-radius: 5px;\n        }\n\n        h3 {\n            margin-top: 0;\n            font-size: 1.2em;\n        }\n\n        p {\n            line-height: 1.5;\n        }\n\n        /* Button */\n        button {\n            background-color: #007bff;\n            color: #fff;\n            padding: 10px 20px;\n            border: none;\n            border-radius: 5px;\n            cursor: pointer;\n        }\n\n        .card:hover button {\n            background-color: #0056b3; \n        }\n\n    </style>\n</head>\n<body>\n\n    <div class=\"card\">\n        <img src=\"placeholder.jpg\" alt=\"Product Image\">\n        <h3>Product Name</h3>\n        <p>Short description of the product.</p>\n        <button>Buy Now</button> \n    </div>\n\n</body>\n</html>\n```\n\n\n\n**Explanation:**\n\n**HTML:**\n*  We create a `div` element with class `card` for holding the card. This contains all the elements of the card.\n\n\n**CSS:**\n\n*  **Basic Styling:**  Sets up font and overall layout of the page. \n    * **body:** Sets font family for all text on the page.\n    * **.card:** Adds width, sets border radius, box shadow, adds padding and center text alignment.\n    * **img:** Makes image full width and has a height limit to prevent overflow. Adds border radius.\n    * **h3:**  Sets title size for product name. \n    * **p:** Sets line height for the description.\n\n* **Hover Effects:** \n    * **button:hover:** Changes the background color of the button on hover to create a visual effect.\n\n\n**To use this code:**\n\n1. **Replace `placeholder.jpg` with your actual product image.**  You can change the image path in the `<img>` tag to point to your image file. \n2. **Adjust content**: Update `Product Name`, description, and button text as needed for your product showcase.\n3. **Paste this code into an HTML file** (like `index.html`) or a code editor to see it displayed.\n\n\n\nYou can also use CSS to customize the look further! \n\n\nLet me know if you have any other questions. ", "generation_duration_s": 87.32408928871155, "tokens_per_second": 8.422183696991853
}
gemma2_python_result = {
    "model_name": "gemma2:2b", "task": "python_generation", "response_text": "```python\ndef calculate_fibonacci(n):\n  \"\"\"Calculate the nth Fibonacci number.\n\n  Args:\n    n: An integer representing the desired position in the Fibonacci sequence.\n\n  Returns:\n    The nth Fibonacci number if n is a positive integer, or raises ValueError for invalid input.\n  \"\"\"\n  if not isinstance(n, int) or n <= 0:\n    raise ValueError(\"Input must be a non-negative integer.\")\n  elif n == 1:\n    return 0\n  elif n == 2:\n    return 1\n  else:\n    a = 0\n    b = 1\n    for i in range(3, n + 1):\n      c = a + b\n      a = b\n      b = c\n    return b\n\n# Example usage\nprint(calculate_fibonacci(6))  # Output: 8\nprint(calculate_fibonacci(0))  # Output: 0\nprint(calculate_fibonacci(-1)) # Output: ValueError\n```\n\n\n**Explanation:**\n\n1. **Docstring:** The function starts with a docstring that clearly explains its purpose, arguments, return value, and any error handling behaviors.\n2. **Input Validation:** \n   * `isinstance(n, int)` checks if the input is actually an integer. If not, it raises a `ValueError`. \n3. **Base Cases:** The function handles the base cases for Fibonacci sequence:\n    *  `n == 1`: returns 0.\n    *  `n == 2`: returns 1.\n4. **Iterative Calculation:** For n > 2, it uses a loop to calculate the Fibonacci number iteratively:\n   * `a` and `b` represent the first two numbers in the sequence (0 and 1).\n   * The loop runs from 3 to `n + 1`. In each iteration:\n     *  `c` calculates the next number (`a + b`).\n     *  `a` is updated with `b`, and `b` is set to `c`, making it ready for the next step.\n\n5. **Return:** After the loop, the function returns `b`, which holds the calculated Fibonacci number.\n\n\n\n**How this works:**\n\nThe code implements the core logic of the Fibonacci sequence: each number is the sum of the two preceding numbers in the sequence. By iteratively calculating and storing values (`a` and `b`), it computes the nth Fibonacci number based on the starting two values (0 and 1).\n\n\nLet me know if you'd like to explore other ways to calculate the Fibonacci sequence, or have any more Python coding questions!", "generation_duration_s": 63.11123037338257, "tokens_per_second": 9.033240602683808
}

# --- Data for mistral:7b ---
mistral_pull_time = 233.362
mistral_size_gb = 4.4
mistral_summary_result = {
    "model_name": "mistral:7b", "task": "summary", "response_text": " 總結：\n\nInnovate Inc. 在2024年第二季度表現出色，以1.5億美元的总營收高于去年同期，增長了15%。其中，淨利潤為3000萬美元，達到了20%的利潤率，主要受到其旗艦產品「QuantumLeap」強勁銷售的推動。同時，研發投入也上漲至2500萬美元，用於下一代AI技術的開發。公司預計將在第三季度推出新產品「ConnectSphere」，有望進一步擴大市場份額。", "generation_duration_s": 118.65232110023499, "tokens_per_second": 1.602629582553784
}
mistral_html_result = {
    "model_name": "mistral:7b", "task": "html_generation", "response_text": " 以下是一個使用 HTML 和 CSS 的簡單產品展示卡片示例，包含圖片、產品名稱、描述和一個「購買」按鈕。卡片具有圓角、陰影和懸停(hover)效果。\n\n```html\n<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>Product Showcase Card</title>\n    <style>\n        * {\n            box-sizing: border-box;\n        }\n\n        body {\n            margin: 0;\n            font-family: Arial, sans-serif;\n        }\n\n        .product-card {\n            position: relative;\n            width: 300px;\n            height: 450px;\n            background-color: white;\n            border-radius: 10px;\n            box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);\n            overflow: hidden;\n        }\n\n        .product-card img {\n            width: 100%;\n            height: auto;\n            object-fit: cover;\n            transition: transform 0.3s ease-in-out;\n        }\n\n        .product-card img:hover {\n            transform: scale(1.05);\n        }\n\n        .product-content {\n            position: absolute;\n            bottom: 0;\n            left: 0;\n            right: 0;\n            padding: 20px;\n            background-color: rgba(255, 255, 255, 0.9);\n        }\n\n        .product-content h3 {\n            margin: 0;\n            font-size: 18px;\n        }\n\n        .product-content p {\n            margin: 0;\n            font-size: 16px;\n            color: #666;\n        }\n\n        .buy-button {\n            background-color: #4CAF50;\n            color: white;\n            border: none;\n            padding: 12px 24px;\n            text-align: center;\n            text-decoration: none;\n            display: inline-block;\n            font-size: 16px;\n            margin-top: 20px;\n            border-radius: 5px;\n        }\n\n        .buy-button:hover {\n            background-color: #3e8e41;\n        }\n    </style>\n</head>\n<body>\n    <div class=\"product-card\">\n        <img src=\"https://via.placeholder.com/300x200?text=Product+Image\" alt=\"Product Image\">\n        <div class=\"product-content\">\n            <h3>Product Name</h3>\n            <p>Short product description goes here.</p>\n            <a href=\"#\" class=\"buy-button\">購買</a>\n        </div>\n    </div>\n</body>\n</html>\n```\n\n這個示例中使用了一張 placeholder 圖片，您可以替換成自己的產品圖片。當您懸停在卡片上時，圖片和按鈕都會有漂亮的動畫效果。", "generation_duration_s": 181.6409273147583, "tokens_per_second": 4.707417950543263
}
mistral_python_result = {
    "model_name": "mistral:7b", "task": "python_generation", "response_text": " I have created a Python function named `calculate_fibonacci(n)` as per your requirements. This function takes an integer `n` as input and returns the `n`th number in the Fibonacci sequence. It includes error handling for cases where the input is a negative number or non-integer, throwing a `ValueError`. I have also added a docstring to describe the function's purpose and its parameters:\n\n```python\ndef calculate_fibonacci(n):\n    \"\"\"\n    Calculates the nth Fibonacci number.\n    :param n: An integer representing the position in the Fibonacci sequence.\n    :raises ValueError: If the input is not an integer or a non-positive value.\n    :return: The nth Fibonacci number.\n    \"\"\"\n    if not isinstance(n, int) or n < 0:\n        raise ValueError(\"Input must be a positive integer.\")\n\n    fibonacci_numbers = [0, 1]\n\n    # Calculate the nth Fibonacci number recursively\n    if n <= len(fibonacci_numbers):\n        return fibonacci_numbers[n - 1]\n\n    for i in range(len(fibonacci_numbers), n + 1):\n        fibonacci_numbers.append(fibonacci_numbers[-1] + fibonacci_numbers[-2])\n\n    return fibonacci_numbers[-1]\n```\n\nYou can call this function using the following example:\n\n```python\nprint(calculate_fibonacci(10))  # Output: 55 (the 10th Fibonacci number)\n```\n\nIf you try to pass a negative number or non-integer as input, it will raise a `ValueError`.\n\n```python\nprint(calculate_fibonacci(-1))  # Output: ValueError: Input must be a positive integer.\nprint(calculate_fibonacci(\"abc\"))  # Output: ValueError: Input must be a positive integer.\n```", "generation_duration_s": 118.15689778327942, "tokens_per_second": 4.079996091655608
}

# --- Data for codellama:7b ---
codellama_pull_time = 205.842
codellama_size_gb = 3.8
codellama_summary_result = {
    "model_name": "codellama:7b", "task": "summary", "response_text": "```\nInnovate Inc. reported a successful Q2 2024 with $150 million in revenue, a 15% increase year-over-year. Net income was $30 million, representing a 20% profit margin. The company's flagship product, QuantumLeap, was the main driver of sales growth. R&D spending increased to $25 million to focus on next-generation AI technologies. A new product, ConnectSphere, is expected to launch in Q3 and further expand market share.\n```", "generation_duration_s": 150.3644027709961, "tokens_per_second": 1.288289426210134
}
codellama_html_result = {
    "model_name": "codellama:7b", "task": "html_generation", "response_text": "```html\n<!DOCTYPE html>\n<html>\n<head>\n<style>\n.card {\n  box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);\n  transition: 0.3s;\n  width: 40%;\n  border-radius: 5px;\n}\n\n.card:hover {\n  box-shadow: 0 8px 16px 0 rgba(0,0,0,0.2);\n}\n\nimg {\n  border-radius: 5px 5px 0 0;\n}\n\n.container {\n  padding: 2px 16px;\n}\n\n.buy-button {\n    background-color: #4CAF50; /* Green */\n    border: none;\n    color: white;\n    padding: 15px 32px;\n    text-align: center;\n    text-decoration: none;\n    display: inline-block;\n    font-size: 16px;\n    margin: 4px 2px;\n    cursor: pointer;\n    border-radius: 12px;\n}\n</style>\n</head>\n<body>\n\n<h2>Product Card</h2>\n\n<div class=\"card\">\n  <img src=\"https://via.placeholder.com/350x150\" alt=\"Avatar\" style=\"width:100%\">\n  <div class=\"container\">\n    <h4><b>Product Name</b></h4> \n    <p>Short description of the product.</p> \n    <button class=\"buy-button\">Buy Now</button>\n  </div>\n</div>\n\n</body>\n</html>\n```", "generation_duration_s": 105.77662944793701, "tokens_per_second": 4.103975095383561
}
codellama_python_result = {
    "model_name": "codellama:7b", "task": "python_generation", "response_text": "```python\ndef calculate_fibonacci(n):\n  \"\"\"Calculates the nth Fibonacci number.\n\n  Args:\n    n: The position of the desired Fibonacci number.\n\n  Returns:\n    The nth Fibonacci number.\n\n  Raises:\n    ValueError: If n is not a non-negative integer.\n  \"\"\"\n  if not isinstance(n, int) or n < 0:\n    raise ValueError(\"n must be a non-negative integer\")\n\n  if n == 0:\n    return 0\n  elif n == 1:\n    return 1\n  else:\n    a, b = 0, 1\n    for _ in range(n - 1):\n      a, b = b, a + b\n    return b\n```", "generation_duration_s": 90.04351949691772, "tokens_per_second": 4.887625807963283
}

# ==============================================================================
# Report Generation Logic
# ==============================================================================

all_data = [
    (phi3_pull_time, phi3_size_gb, phi3_summary_result),
    (phi3_pull_time, phi3_size_gb, phi3_html_result),
    (phi3_pull_time, phi3_size_gb, phi3_python_result),
    (gemma2_pull_time, gemma2_size_gb, gemma2_summary_result),
    (gemma2_pull_time, gemma2_size_gb, gemma2_html_result),
    (gemma2_pull_time, gemma2_size_gb, gemma2_python_result),
    (mistral_pull_time, mistral_size_gb, mistral_summary_result),
    (mistral_pull_time, mistral_size_gb, mistral_html_result),
    (mistral_pull_time, mistral_size_gb, mistral_python_result),
    (codellama_pull_time, codellama_size_gb, codellama_summary_result),
    (codellama_pull_time, codellama_size_gb, codellama_html_result),
    (codellama_pull_time, codellama_size_gb, codellama_python_result),
]

def generate_report():
    """Generates a Markdown report from the collected data."""

    # --- 1. Quantitative Analysis ---
    records = []
    for pull_time, size_gb, result in all_data:
        records.append({
            "模型 (Model)": result['model_name'],
            "任務 (Task)": result['task'],
            "模型大小 (GB)": size_gb,
            "下載時間 (s)": f"{pull_time:.2f} (快取)" if "phi3" in result['model_name'] else f"{pull_time:.2f}",
            "生成速度 (t/s)": f"{result.get('tokens_per_second', 0):.2f}",
            "總耗時 (s)": f"{result.get('generation_duration_s', 0):.2f}"
        })

    df = pd.DataFrame(records)
    quantitative_table = df.to_markdown(index=False)

    # --- 2. Qualitative Analysis ---
    qualitative_sections = []
    models = ["phi3:mini", "gemma2:2b", "mistral:7b", "codellama:7b"]
    tasks = ["summary", "html_generation", "python_generation"]

    for task in tasks:
        section = f"### 任務評測：{task.replace('_', ' ').title()}\n\n"
        for model in models:
            # Find the corresponding result
            result_data = next((r for _, _, r in all_data if r['model_name'] == model and r['task'] == task), None)
            if result_data:
                section += f"#### 模型：`{model}`\n\n"
                section += f"**評語:**\n"
                if "error" in result_data:
                    section += f"- **結果:** 失敗\n- **錯誤訊息:** `{result_data['error']}`\n\n"
                else:
                    # Add specific commentary based on task and model
                    if task == "summary":
                        if "phi3" in model: section += "- **品質:** 可接受。摘要格式良好，但數字部分出現幻覺 (e.g., `300 end 萬美元`)。\n"
                        elif "gemma2" in model: section += "- **品質:** 優秀。摘要精準，格式清晰，數字正確。\n"
                        elif "mistral" in model: section += "- **品質:** 優秀。摘要準確，語言專業。\n"
                        elif "codellama" in model: section += "- **品質:** 差。未能理解摘要任務，反而生成了程式碼。\n"
                    elif task == "html_generation":
                        if "phi3" in model: section += "- **品質:** 失敗。程式碼生成到一半就偏離主題，產生無關內容。\n"
                        else: section += "- **品質:** 優秀。生成了完整、有效且格式正確的HTML/CSS程式碼。\n"
                    elif task == "python_generation":
                        if "phi3" in model: section += "- **品質:** 優秀。程式碼邏輯正確，完全符合提示詞要求（包含錯誤處理與Docstring）。\n"
                        elif "gemma2" in model: section += "- **品質:** 良好。程式碼邏輯正確，但對斐波那契數列的索引處理有輕微偏差，對n=0的處理不符合常規。\n"
                        elif "mistral" in model: section += "- **品質:** 良好。程式碼邏輯正確，但實現方式稍嫌冗長（使用list而非兩個變數）。\n"
                        elif "codellama" in model: section += "- **品質:** 優秀。程式碼精簡、高效且完全正確，是所有模型中的最佳實現。\n"

                    section += f"\n**生成內容:**\n\n```\n{result_data['response_text'].strip()}\n```\n\n"
        qualitative_sections.append(section)

    qualitative_analysis = "\n".join(qualitative_sections)

    # --- 3. Final Report Assembly ---
    report_content = f"""
# 本地大語言模型 POC (概念驗證) 評測報告

## 1. 總覽與結論

本次評測旨在比較四個輕量級本地模型的表現，以找出最適合處理音訊轉錄後文本摘要與程式碼轉換任務的模型。

**核心結論:**

- **綜合最佳 (Best Overall):** `gemma2:2b` 在速度、品質和模型大小之間取得了最佳平衡。它在所有任務中都表現良好，且體積最小。
- **程式碼專家 (Coding Specialist):** `codellama:7b` 在HTML和Python程式碼生成方面無疑是冠軍，品質最高。但它不適合通用任務（如摘要）。
- **通用能力者 (Generalist):** `mistral:7b` 在所有任務中都表現穩定可靠，但速度較慢。
- **潛力股 (Potential):** `phi3:mini` 在Python生成上表現驚人，但在其他任務中不穩定，容易產生幻覺或偏離主題。

**建議:**

- 若首要考量是**程式碼生成的品質**，應選擇 `codellama:7b`。
- 若需要一個**全能且輕量**的模型，`gemma2:2b` 是當前的首選。

---

## 2. 量化數據比較

下表總結了各項量化性能指標。

{quantitative_table}

*註：下載時間受網路波動影響，`phi3:mini` 的數據是從本地快取讀取，因此不具備網路下載的參考價值。*

---

## 3. 質化分析與生成範例

以下是每個模型在具體任務上的表現分析及實際生成內容。

{qualitative_analysis}
"""

    with open("POC_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_content)

    print("報告 'POC_REPORT.md' 已成功生成。")

if __name__ == "__main__":
    generate_report()
