import pandas as pd
import dataframe_image as dfi
import matplotlib.pyplot as plt
import io

def install_dependencies():
    """Install necessary libraries if they are not already installed."""
    try:
        import pandas
    except ImportError:
        print("Installing pandas...")
        import pip
        pip.main(['install', 'pandas'])
    try:
        import dataframe_image
    except ImportError:
        print("Installing dataframe_image...")
        import pip
        pip.main(['install', 'dataframe_image'])
    try:
        import matplotlib
    except ImportError:
        print("Installing matplotlib...")
        import pip
        pip.main(['install', 'matplotlib'])


def create_summary_table_image():
    """
    Creates a PNG image from the financial summary text.
    The text is from the successful output of the gemma2:2b model.
    """
    summary_data = {
        "項目": [
            "營收表現",
            "利潤與毛利率",
            "未來展望"
        ],
        "內容": [
            "第二季營收150億美元，年增12%，優於市場預期。",
            "淨利潤30億美元，年減5%；毛利率從55%下滑至48%。",
            "預計第三季營收持平，將持續投資先進製程。"
        ],
        "分析": [
            "營收增長強勁，顯示市場需求穩健。",
            "高額研發投入與供應鏈壓力侵蝕獲利能力。",
            "短期營收趨於平穩，公司著眼長期技術領導地位。"
        ]
    }
    df = pd.DataFrame(summary_data)

    # Style the dataframe for better presentation
    df_styled = df.style.set_properties(**{
        'border': '1px solid black',
        'font-size': '12pt',
        'text-align': 'left',
        'padding': '10px'
    }).set_table_styles([
        {'selector': 'th', 'props': [('background-color', '#f2f2f2'), ('font-weight', 'bold')]}
    ]).hide(axis="index") # Hide the default index

    dfi.export(df_styled, 'summary_table.png', table_conversion='matplotlib')
    print("Successfully created summary_table.png")

def create_revenue_chart_image():
    """
    Creates a bar chart PNG from the quarterly revenue data.
    This demonstrates the Python part of the charting workflow.
    """
    # Data that was intended for the LLM
    csv_data = """季度,營收(百萬)
Q1,6.5
Q2,8.2
Q3,7.8
Q4,9.1
"""
    # Use pandas to read the CSV data
    df = pd.read_csv(io.StringIO(csv_data))

    # Create the plot
    plt.figure(figsize=(10, 6))
    bars = plt.bar(df['季度'], df['營收(百萬)'], color=['#4c72b0', '#55a868', '#c44e52', '#8172b2'])

    # Add titles and labels with font properties for Chinese characters
    plt.title('2024 季度營收', fontsize=16, fontname='SimHei')
    plt.xlabel('季度', fontsize=12, fontname='SimHei')
    plt.ylabel('營收 (百萬)', fontsize=12, fontname='SimHei')
    plt.xticks(rotation=0, fontsize=10)
    plt.yticks(fontsize=10)
    plt.grid(axis='y', linestyle='--', alpha=0.7)

    # Add data labels on top of each bar
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2.0, yval, f'{yval}M', va='bottom', ha='center', fontsize=10)

    plt.tight_layout()
    plt.savefig('revenue_chart.png')
    print("Successfully created revenue_chart.png")


if __name__ == '__main__':
    # Note: In a real environment, dependency installation should be handled
    # by a requirements.txt or pyproject.toml file, not in the script itself.
    # This is done here for demonstration purposes in a self-contained script.
    # install_dependencies() # Commented out as dependencies should be pre-installed in the environment

    # Since we can't be sure about the environment, let's try to set a font that supports Chinese
    try:
        plt.rcParams['font.sans-serif'] = ['SimHei']  # A common font for Chinese characters
        plt.rcParams['axes.unicode_minus'] = False # To display negative signs correctly
    except Exception as e:
        print(f"Could not set Chinese font: {e}. The chart labels might not display correctly.")

    create_summary_table_image()
    create_revenue_chart_image()
