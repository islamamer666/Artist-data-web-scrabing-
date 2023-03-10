from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import re, time, logging
from bs4 import BeautifulSoup
import pymongo
import boto3

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)

class WikipediaScraper():

    def __init__(self, chromedriver_path=None):
        options = Options()
        options.headless = True
        options.add_argument("window-size=1920,1080")
        options.add_argument("--log-level=3")
        options.add_argument("--no-sandbox")
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36")
        if chromedriver_path:
            self.driver = webdriver.Chrome(executable_path=chromedriver_path, options=options)
        else:
            self.driver = webdriver.Chrome(executable_path=ChromeDriverManager().install(), options=options)
        self.driver.get("https://www.wikipedia.org/")

    def scrape_artist_intro(self, artist_name, keywords=[]):

        search_input = self.driver.find_element(By.ID, "searchInput")
        search_input.clear()
        self.driver.find_element(By.TAG_NAME, "h1").click()
        time.sleep(1)
        search_input.send_keys(artist_name)
        time.sleep(1)
        try:
            dropdown = WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CLASS_NAME, "suggestions-dropdown")))
        except:
            return None, None, None
        suggestions = dropdown.find_elements(By.CLASS_NAME, "suggestion-link")
        found = False
        keywords += ["art", "paint", "sculp"]
        for suggestion in suggestions:
            if suggestion.find_element(By.CLASS_NAME, "suggestion-title").text.lower().strip() == artist_name.lower() and self.__check_keywords(suggestion.find_element(By.CLASS_NAME, "suggestion-description").text, keywords):
                found = suggestion
                break
        if not found and suggestions:
            found = suggestions[0]
        if not found:
            return None, None, None
        
        page_link = found.get_attribute("href")
        self.driver.execute_script('''window.open("","_blank");''')
        self.driver.switch_to.window(self.driver.window_handles[1])
        self.driver.get(page_link)
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        toc = soup.find(id="toc")
        pattern = r'\[.*?\]'
        intro = ""
        if toc:
            ps = toc.find_all_previous("p")
            if ps:
                ps.reverse()
                for p in ps:
                    intro += p.text.strip()

        known_for = ""
        try:
            rows = self.driver.find_element(By.CLASS_NAME, "infobox").find_elements(By.TAG_NAME, "tr")
            for row in rows:
                try:
                    if row.find_element(By.TAG_NAME, "th").text.strip().lower() == "known for":
                        known_for = row.find_element(By.TAG_NAME, "td").text.strip()
                        print(known_for)
                except:
                    pass
        except:
            pass
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])
        return re.sub(pattern, '', intro), page_link, known_for

    def __check_keywords(self, text, keywords):

        for keyword in keywords:
            if keyword.lower() in text.lower():
                return True

        return False



if __name__ == "__main__":

    scraper = WikipediaScraper()
    
    myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    s3_client = boto3.client('s3', aws_access_key_id="AKIA2Z27IODYMF7EBS52", aws_secret_access_key="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")
    bucket_name = "dotartimages"

    mydb = myclient["artistDB"]
    mycol = mydb["artistCollection"]

    while True:
        doc = mycol.find_one({ "$and": [ {"artistDisplayName" : { "$nin": [None, ""]} }, {"artistDisplayName": { "$not": { "$regex" : "Anonymous"}}}, { "artistWikipediaKnownFor": { "$exists": False} }]})
        if not doc:
            break
        logging.info("Getting Wikipedia for " + doc['artistDisplayName'])
        while True:
            try:
                intro, wiki_url, known_for = scraper.scrape_artist_intro(doc['artistDisplayName'])
                break
            except Exception as e:
                logging.error("Error: " + str(e))
                logging.info("Restarting chrome")
                try:
                    scraper.driver.quit()
                except:
                    pass
                scraper = WikipediaScraper()
        if wiki_url:
            logging.info("Found Wikipedia for " + doc['artistDisplayName'])
            result = mycol.update_many({ "artistDisplayName": doc['artistDisplayName']}, { "$set" : {"artistWikipediaURL": wiki_url, "artistWikipediaIntro": intro, "artistWikipediaKnownFor": known_for }})
        else:
            logging.info("Couldn't Find Wikipedia for " + doc['artistDisplayName'])
            result = mycol.update_many({ "artistDisplayName": doc['artistDisplayName']}, { "$set" : {"artistWikipediaURL": "", "artistWikipediaIntro": "", "artistWikipediaKnownFor": "" }})
        logging.info(f"{result.matched_count} records updated.")
    scraper.driver.quit()