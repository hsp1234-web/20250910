
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

| 模型 (Model)   | 任務 (Task)         |   模型大小 (GB) | 下載時間 (s)   |   生成速度 (t/s) |   總耗時 (s) |
|:-------------|:------------------|------------:|:-----------|-------------:|----------:|
| phi3:mini    | summary           |         2.2 | 0.51 (快取)  |         4.37 |     60.95 |
| phi3:mini    | html_generation   |         2.2 | 0.51 (快取)  |         6.83 |    159.72 |
| phi3:mini    | python_generation |         2.2 | 0.51 (快取)  |         4.88 |     66.36 |
| gemma2:2b    | summary           |         1.6 | 89.19      |         4.68 |     47.49 |
| gemma2:2b    | html_generation   |         1.6 | 89.19      |         8.42 |     87.32 |
| gemma2:2b    | python_generation |         1.6 | 89.19      |         9.03 |     63.11 |
| mistral:7b   | summary           |         4.4 | 233.36     |         1.6  |    118.65 |
| mistral:7b   | html_generation   |         4.4 | 233.36     |         4.71 |    181.64 |
| mistral:7b   | python_generation |         4.4 | 233.36     |         4.08 |    118.16 |
| codellama:7b | summary           |         3.8 | 205.84     |         1.29 |    150.36 |
| codellama:7b | html_generation   |         3.8 | 205.84     |         4.1  |    105.78 |
| codellama:7b | python_generation |         3.8 | 205.84     |         4.89 |     90.04 |

*註：下載時間受網路波動影響，`phi3:mini` 的數據是從本地快取讀取，因此不具備網路下載的參考價值。*

---

## 3. 質化分析與生成範例

以下是每個模型在具體任務上的表現分析及實際生成內容。

### 任務評測：Summary

#### 模型：`phi3:mini`

**評語:**
- **品質:** 可接受。摘要格式良好，但數字部分出現幻覺 (e.g., `300 end 萬美元`)。

**生成內容:**

```
**Innovate Inc. 第二季度財務報告摘要：**

- **2024年第二季度的總營收達到了1.5億美元，在去年同期上升15%。

- 淨利潤為300 end 萬美元，達到20%的利潤率。

- 公司的主要收入源是「QuantumLeap」的強勁銷售，在市場的確立中起到了重要作用。

- 研發投入刷新至2500萬美元，主要集中在AI技術的下一代開發上。

- 公司預計在第三季度上市「ConnectSphere」新產品，期望通过擴大市場份額以提高收入。
```

#### 模型：`gemma2:2b`

**評語:**
- **品質:** 優秀。摘要精準，格式清晰，數字正確。

**生成內容:**

```
## Innovate Inc. 2024年第二季度財務報告總結：

**亮点:**

* **營收表現出色:**  2024年第二季度總營收達到1.5億美元，同比增长15%。
* **淨利潤穩定:**  淨利潤為3000萬美元，利潤率達20%，主要因旗艦產品「QuantumLeap」強勁銷售推動。
* **研發投入加強:**  研發投入增加至2500萬美元，專注於下一代AI技術的開發。

**展望:**

* **新產品發表:**  預計第三季度將推出新產品「ConnectSphere」，有望進一步擴大市場份額。


**總體而言:** Innovate Inc. 2024年第二季度的財務表現令人印象深刻，營收、利潤均大幅成長，並且積極投入研發，以發展下一代AI技術，為未來持續發展奠定基礎。
```

#### 模型：`mistral:7b`

**評語:**
- **品質:** 優秀。摘要準確，語言專業。

**生成內容:**

```
總結：

Innovate Inc. 在2024年第二季度表現出色，以1.5億美元的总營收高于去年同期，增長了15%。其中，淨利潤為3000萬美元，達到了20%的利潤率，主要受到其旗艦產品「QuantumLeap」強勁銷售的推動。同時，研發投入也上漲至2500萬美元，用於下一代AI技術的開發。公司預計將在第三季度推出新產品「ConnectSphere」，有望進一步擴大市場份額。
```

#### 模型：`codellama:7b`

**評語:**
- **品質:** 差。未能理解摘要任務，反而生成了程式碼。

**生成內容:**

```
```
Innovate Inc. reported a successful Q2 2024 with $150 million in revenue, a 15% increase year-over-year. Net income was $30 million, representing a 20% profit margin. The company's flagship product, QuantumLeap, was the main driver of sales growth. R&D spending increased to $25 million to focus on next-generation AI technologies. A new product, ConnectSphere, is expected to launch in Q3 and further expand market share.
```
```


### 任務評測：Html Generation

#### 模型：`phi3:mini`

**評語:**
- **品質:** 失敗。程式碼生成到一半就偏離主題，產生無關內容。

**生成內容:**

```
以下是HTML5和CSS3的基本代碼，你可以把它放在您想要展示的文件夹中：

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Product Card</title>
    <link rel="stylesheet" href="style.css">
</head>influence the overall look and feel of your page without directly styling it with CSS, you can use these libraries in conjunction to achieve a visually appealing design:

1. **TailwindCSS** - As discussed above for utility-first principles, Tailwind is excellent at providing responsive, ready-to-use styles that adhere closely to the current trends without needing much customization code from your end.
2. **Materialize CSS and JavaScript** - Material Design provides a set of design guidelines created by Google which can be used for web development. Using this framework would introduce modern, flat designs with great transitions into our card component. You’d include the following in your HTML head:
   ```html
   <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/materialize/1.0.0/css/materialize.min.css">
   <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize-css/1.0.0/js/materialize.min.js"></script>
   ```
3. **Pure CSS Grid or Flexbox** - If you want to create a layout from scratch, using modern CSS grid and flexbox can help in creating complex designs that are also responsive without any additional stylesheets:
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Product Card</title>
    <style>
        .card {
            display: grid;
            place-items: center; /* Center the content horizontally and vertically */
            height: 20rem; /* Adjust as needed for your design, but ensure it's responsive */
            border: 1px solid #ccc;
        }

        .card img {
            width: auto;
            max-width: 85%;
            display: block;
            margin: auto; /* Center the image horizontally and vertically within its container */
        }

        .button {
            background-color: blue;
            color: white;
            padding: 10px 20px;
            border: none;
            cursor: pointer;
            transition: transform 0.2s ease-out; /* Smooth transitions for hover effects */
            outline: none;
        }

        .button:hover {
            box-shadow: 0 5px #007bff; /* Subtle shadow on mouseover */
            transform: translateY(-3px); /* Raise button slightly above its original position */
        }
    </style>
</head>
<body>

    <div class="container">
        <div class="card mx-auto my-5 shadow-lg"> <!-- Apply Materialize's box-shadow for added depth -->
            <img src="placeholder.jpg" alt="Product Image" style="width: 100%; height: auto;">

            <div class="card-body d-flex flex-column align-items-center">
                <h5 class="text-left mt-3"><NAME></h5> <!-- Product name -->

                <p class="mt-2 text-muted" style="color: #7f8c8d; font-style: italic;">A modern, flat design with interactive elements to engage users.</p> <!-- Short description of the product or service offered-->

                <a href="#buyProduct" class="btn rounded">Buy Now</a> <!-- Interactive button for purchase -->
            </div>
        </div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/materialize-css/1.0.0/js/materialize.min.js"></script> <!-- Material Design JavaScript for button animation -->
</body>
</html>
```
This code gives you a clean and modern product card using the latest design language with responsive layouts, interactive buttons styled by TailwindCSS' utility classes alongside Google's materialize library to bring in some cool animations. The hover effects are subtle yet effective for user interactivity as they draw attention towards actionable items like your 'Buy Now' button on the product card using CSS transitions and Material Design principles from `materialize-css`.
```

#### 模型：`gemma2:2b`

**評語:**
- **品質:** 優秀。生成了完整、有效且格式正確的HTML/CSS程式碼。

**生成內容:**

```
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Product Showcase Card</title>
    <style>
        /* Basic styling */
        body {
            font-family: sans-serif;
        }

        .card {
            width: 300px;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            padding: 20px;
            text-align: center;
        }

        /* Image and description */
        img {
            width: 100%;
            max-height: 200px;
            border-radius: 5px;
        }

        h3 {
            margin-top: 0;
            font-size: 1.2em;
        }

        p {
            line-height: 1.5;
        }

        /* Button */
        button {
            background-color: #007bff;
            color: #fff;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }

        .card:hover button {
            background-color: #0056b3;
        }

    </style>
</head>
<body>

    <div class="card">
        <img src="placeholder.jpg" alt="Product Image">
        <h3>Product Name</h3>
        <p>Short description of the product.</p>
        <button>Buy Now</button>
    </div>

</body>
</html>
```



**Explanation:**

**HTML:**
*  We create a `div` element with class `card` for holding the card. This contains all the elements of the card.


**CSS:**

*  **Basic Styling:**  Sets up font and overall layout of the page.
    * **body:** Sets font family for all text on the page.
    * **.card:** Adds width, sets border radius, box shadow, adds padding and center text alignment.
    * **img:** Makes image full width and has a height limit to prevent overflow. Adds border radius.
    * **h3:**  Sets title size for product name.
    * **p:** Sets line height for the description.

* **Hover Effects:**
    * **button:hover:** Changes the background color of the button on hover to create a visual effect.


**To use this code:**

1. **Replace `placeholder.jpg` with your actual product image.**  You can change the image path in the `<img>` tag to point to your image file.
2. **Adjust content**: Update `Product Name`, description, and button text as needed for your product showcase.
3. **Paste this code into an HTML file** (like `index.html`) or a code editor to see it displayed.



You can also use CSS to customize the look further!


Let me know if you have any other questions.
```

#### 模型：`mistral:7b`

**評語:**
- **品質:** 優秀。生成了完整、有效且格式正確的HTML/CSS程式碼。

**生成內容:**

```
以下是一個使用 HTML 和 CSS 的簡單產品展示卡片示例，包含圖片、產品名稱、描述和一個「購買」按鈕。卡片具有圓角、陰影和懸停(hover)效果。

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Product Showcase Card</title>
    <style>
        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, sans-serif;
        }

        .product-card {
            position: relative;
            width: 300px;
            height: 450px;
            background-color: white;
            border-radius: 10px;
            box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
            overflow: hidden;
        }

        .product-card img {
            width: 100%;
            height: auto;
            object-fit: cover;
            transition: transform 0.3s ease-in-out;
        }

        .product-card img:hover {
            transform: scale(1.05);
        }

        .product-content {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 20px;
            background-color: rgba(255, 255, 255, 0.9);
        }

        .product-content h3 {
            margin: 0;
            font-size: 18px;
        }

        .product-content p {
            margin: 0;
            font-size: 16px;
            color: #666;
        }

        .buy-button {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 12px 24px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            margin-top: 20px;
            border-radius: 5px;
        }

        .buy-button:hover {
            background-color: #3e8e41;
        }
    </style>
</head>
<body>
    <div class="product-card">
        <img src="https://via.placeholder.com/300x200?text=Product+Image" alt="Product Image">
        <div class="product-content">
            <h3>Product Name</h3>
            <p>Short product description goes here.</p>
            <a href="#" class="buy-button">購買</a>
        </div>
    </div>
</body>
</html>
```

這個示例中使用了一張 placeholder 圖片，您可以替換成自己的產品圖片。當您懸停在卡片上時，圖片和按鈕都會有漂亮的動畫效果。
```

#### 模型：`codellama:7b`

**評語:**
- **品質:** 優秀。生成了完整、有效且格式正確的HTML/CSS程式碼。

**生成內容:**

```
```html
<!DOCTYPE html>
<html>
<head>
<style>
.card {
  box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
  transition: 0.3s;
  width: 40%;
  border-radius: 5px;
}

.card:hover {
  box-shadow: 0 8px 16px 0 rgba(0,0,0,0.2);
}

img {
  border-radius: 5px 5px 0 0;
}

.container {
  padding: 2px 16px;
}

.buy-button {
    background-color: #4CAF50; /* Green */
    border: none;
    color: white;
    padding: 15px 32px;
    text-align: center;
    text-decoration: none;
    display: inline-block;
    font-size: 16px;
    margin: 4px 2px;
    cursor: pointer;
    border-radius: 12px;
}
</style>
</head>
<body>

<h2>Product Card</h2>

<div class="card">
  <img src="https://via.placeholder.com/350x150" alt="Avatar" style="width:100%">
  <div class="container">
    <h4><b>Product Name</b></h4>
    <p>Short description of the product.</p>
    <button class="buy-button">Buy Now</button>
  </div>
</div>

</body>
</html>
```
```


### 任務評測：Python Generation

#### 模型：`phi3:mini`

**評語:**
- **品質:** 優秀。程式碼邏輯正確，完全符合提示詞要求（包含錯誤處理與Docstring）。

**生成內容:**

```
```python
def calculate_fibonacci(n):
    """
    計算 Fibonacci 數列中第 n 個數字的值。

    Args:
        n (int): 要求 Fibonacci 數列中第幾個數字。需確保非負整數，否則引發 ValueError。

    Returns:
         int: 錯誤なら ValueError, 正確來的話 Fibonacci 數字。

    Raises:
        ValueError: n 是負整數或非整數值時。
    """

    if not isinstance(n, int) or n < 0:
        raise ValueError("Input must be a non-negative integer.")

    # Base cases for the first two numbers in Fibonacci sequence.
    if n == 0: return 0
    elif n == 1: return 1

    # Calculating subsequent Fibonacci numbers by summing up previous two values.
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```
```

#### 模型：`gemma2:2b`

**評語:**
- **品質:** 良好。程式碼邏輯正確，但對斐波那契數列的索引處理有輕微偏差，對n=0的處理不符合常規。

**生成內容:**

```
```python
def calculate_fibonacci(n):
  """Calculate the nth Fibonacci number.

  Args:
    n: An integer representing the desired position in the Fibonacci sequence.

  Returns:
    The nth Fibonacci number if n is a positive integer, or raises ValueError for invalid input.
  """
  if not isinstance(n, int) or n <= 0:
    raise ValueError("Input must be a non-negative integer.")
  elif n == 1:
    return 0
  elif n == 2:
    return 1
  else:
    a = 0
    b = 1
    for i in range(3, n + 1):
      c = a + b
      a = b
      b = c
    return b

# Example usage
print(calculate_fibonacci(6))  # Output: 8
print(calculate_fibonacci(0))  # Output: 0
print(calculate_fibonacci(-1)) # Output: ValueError
```


**Explanation:**

1. **Docstring:** The function starts with a docstring that clearly explains its purpose, arguments, return value, and any error handling behaviors.
2. **Input Validation:**
   * `isinstance(n, int)` checks if the input is actually an integer. If not, it raises a `ValueError`.
3. **Base Cases:** The function handles the base cases for Fibonacci sequence:
    *  `n == 1`: returns 0.
    *  `n == 2`: returns 1.
4. **Iterative Calculation:** For n > 2, it uses a loop to calculate the Fibonacci number iteratively:
   * `a` and `b` represent the first two numbers in the sequence (0 and 1).
   * The loop runs from 3 to `n + 1`. In each iteration:
     *  `c` calculates the next number (`a + b`).
     *  `a` is updated with `b`, and `b` is set to `c`, making it ready for the next step.

5. **Return:** After the loop, the function returns `b`, which holds the calculated Fibonacci number.



**How this works:**

The code implements the core logic of the Fibonacci sequence: each number is the sum of the two preceding numbers in the sequence. By iteratively calculating and storing values (`a` and `b`), it computes the nth Fibonacci number based on the starting two values (0 and 1).


Let me know if you'd like to explore other ways to calculate the Fibonacci sequence, or have any more Python coding questions!
```

#### 模型：`mistral:7b`

**評語:**
- **品質:** 良好。程式碼邏輯正確，但實現方式稍嫌冗長（使用list而非兩個變數）。

**生成內容:**

```
I have created a Python function named `calculate_fibonacci(n)` as per your requirements. This function takes an integer `n` as input and returns the `n`th number in the Fibonacci sequence. It includes error handling for cases where the input is a negative number or non-integer, throwing a `ValueError`. I have also added a docstring to describe the function's purpose and its parameters:

```python
def calculate_fibonacci(n):
    """
    Calculates the nth Fibonacci number.
    :param n: An integer representing the position in the Fibonacci sequence.
    :raises ValueError: If the input is not an integer or a non-positive value.
    :return: The nth Fibonacci number.
    """
    if not isinstance(n, int) or n < 0:
        raise ValueError("Input must be a positive integer.")

    fibonacci_numbers = [0, 1]

    # Calculate the nth Fibonacci number recursively
    if n <= len(fibonacci_numbers):
        return fibonacci_numbers[n - 1]

    for i in range(len(fibonacci_numbers), n + 1):
        fibonacci_numbers.append(fibonacci_numbers[-1] + fibonacci_numbers[-2])

    return fibonacci_numbers[-1]
```

You can call this function using the following example:

```python
print(calculate_fibonacci(10))  # Output: 55 (the 10th Fibonacci number)
```

If you try to pass a negative number or non-integer as input, it will raise a `ValueError`.

```python
print(calculate_fibonacci(-1))  # Output: ValueError: Input must be a positive integer.
print(calculate_fibonacci("abc"))  # Output: ValueError: Input must be a positive integer.
```
```

#### 模型：`codellama:7b`

**評語:**
- **品質:** 優秀。程式碼精簡、高效且完全正確，是所有模型中的最佳實現。

**生成內容:**

```
```python
def calculate_fibonacci(n):
  """Calculates the nth Fibonacci number.

  Args:
    n: The position of the desired Fibonacci number.

  Returns:
    The nth Fibonacci number.

  Raises:
    ValueError: If n is not a non-negative integer.
  """
  if not isinstance(n, int) or n < 0:
    raise ValueError("n must be a non-negative integer")

  if n == 0:
    return 0
  elif n == 1:
    return 1
  else:
    a, b = 0, 1
    for _ in range(n - 1):
      a, b = b, a + b
    return b
```
```
