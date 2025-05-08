import sys


def main():
    api_url = sys.argv[1]
    template_path = "../../website/index.template.html"
    index_path = "../../website/index.html"

    with open(template_path, "r", encoding="utf-8") as file:
        content = file.read()

    content = content.replace("__API_URL_PLACEHOLDER__", api_url)

    with open(index_path, "w", encoding="utf-8") as file:
        file.write(content)

    print("API URL dynamically injected into website/index.html")

if __name__ == "__main__":
    main()



