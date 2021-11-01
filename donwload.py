import sys,getopt,os
from threading import Thread,Lock
import requests,time
lock=Lock()

is_download=False
output_dir=os.path.dirname(os.path.abspath(__file__))
query=None
num_of_connection=1
num_of_parts_per_download=1
workload=[]
failures=[]

c_red="\033[1;31m"
c_green="\033[1;32m"
c_yellow="\033[1;33m"
c_blue="\033[1;34m"
c_magenta="\033[1;35m"
c_cyan="\033[1;36m"
c_reset="\033[0m"

def usage():
    print("""
    ani_down.py [options] [arguments]
    Options:
    -d : Followed by the name of the anime to download.
    -q : followed by the name of the anime to query.
    """)

try:    
    opts, args=getopt.getopt(sys.argv[1:],shortopts="q:hc:o:d:c:p:",longopts=["download=","query=","help","output=","connections="])
except getopt.GetoptError as err:
    print(err) 
    usage()
    sys.exit(1)

for opt, arg in opts:
    if opt in ("-d","--download"):
        is_download=True
        query=arg
    elif opt in ("-o","--output"):
        output_dir=os.path.abspath(arg)
    elif opt in ("-c","--connections"):
        num_of_connection=int(arg)
    elif opt in ("-p"):
        num_of_parts_per_download=int(arg)
    elif opt in ("-h", "--help"):
        usage()
        sys.exit()

if output_dir[-1]=="/":
    output_dir = output_dir[:-1]

def get_search_query():
    return input("Search Anime: ")

def search_anime(query):
    query = query.replace(" ","-")
    # print(query)
    command=f"""curl -s https://gogoanime.pe//search.html -G -d keyword={query} | sed -n -E 's_^[[:space:]]*<a href="/category/([^"]*)" title="([^"]*)".*_\\1_p'"""
    p=os.popen(command)
    result=p.read()
    p.close()
    return result.split("\n")[:-1]
    # print(result)

def search_last_ep(anime_id):
    command=f"""curl -s "https://gogoanime.pe/category/{anime_id}\"""" + """|sed -n -E '
		/^[[:space:]]*<a href="#" class="active" ep_start/{
		s/.* '\\''([0-9]*)'\\'' ep_end = '\\''([0-9]*)'\\''.*/\\2/p
		q
		}
		'
    """
    p=os.popen(command)
    lst=int(p.read())
    p.close()
    return lst

def anime_selection(result):
    for count, value in enumerate(result):
        print(f"{c_blue}[{c_cyan}{count}{c_blue}] {c_yellow}{value}{c_reset}")
    choice=None
    while(True):
        choice=int(input(f"{c_blue}Enter number: {c_reset}"))
        if 0<=choice<=len(result):
            if search_last_ep(result[choice])==0:
                print(f"{c_red}No episodes are found for this anime...{c_reset}")
            else:
                break
        else:
            print(f"{c_red}invalid choice.{c_reset}")
    return choice

def episode_selection(result,choice):
    if is_download:
        print("Range of episodes can be specified: start_number end_number")
    inp=input(f"{c_blue}Choose episode [{c_cyan}1-{search_last_ep(result[choice])}{c_blue}]: {c_reset}")
    start_ep=int(inp.split()[0])
    if is_download:
        if len(inp.split())>1:
            end_ep=int(inp.split()[1])
        else:
            end_ep=start_ep
        if start_ep not in range(1,search_last_ep(result[choice])+1) and end_ep not in range(1,search_last_ep(result[choice])+1):
            return episode_selection(result,choice)
        return start_ep, end_ep
    if start_ep not in range(1,search_last_ep(result[choice])+1):
        return episode_selection(result,choice)
    return start_ep

def get_dpage_link(anime_id,episode):
    command=f"""
    curl -s "https://gogoanime.pe/{anime_id}-episode-{episode}" """ + """ |
	sed -n -E '
		/^[[:space:]]*<li class="dowloads">/{
		s/.*href="([^"]*)".*/\\1/p
		q
		}'
    """
    p=os.popen(command)
    dpage_link=p.read()
    p.close()
    return dpage_link

def get_video_link(dpage_url):
    if dpage_url[-1]=="\n":
        dpage_url = dpage_url[:-1]
    command=f"""
    curl -s "{dpage_url}" """ + """|
	sed -n -E '
		/href="([^"]*)" download>Download/{
		s/href="([^"]*)" download>Download/\\1/p
		q
		}' | tr -d ' '
    """
    p=os.popen(command)
    vid_url=p.read()
    p.close()

    if "streamtape" in vid_url:
        print("scrapping streamtape...")
        command=f"""
        curl -s "{vid_url}" """ + """| sed -n -E '
            /^<script>document/{
            s/^[^"]*"([^"]*)" \\+ '\\''([^'\\'']*).*/https:\\1\\2\\&dl=1/p
            q
            }
        '
        """

    return vid_url

def download_video(result,choice,episode):
    print(f"{c_green}Getting data for episode {episode} {c_reset}")
    dpage_url=get_dpage_link(result[choice],episode)
    if dpage_url[-1]=="\n":
        dpage_url=dpage_url[:-1]
    video_url=get_video_link(dpage_url)
    if video_url[-1]=="\n":
        video_url=video_url[:-1]

    # print(f"{c_yellow}dpage_url:{dpage_url}{c_reset}")
    # print(f"{c_yellow}video_url:{video_url}{c_reset}")

    print(f"{c_green}Donwloading episode {episode}{c_reset}")
    header={'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36',
        "Accept-Encoding": "gzip, deflate, br",
        }
    header["Referer"]=str(dpage_url[:-1])
    return requests.get(url=video_url,headers=header,stream=True)

def download(result,choice):
    while(True):
        lock.acquire()
        if len(workload)!=0:
            episode=workload.pop(0)
            lock.release()
        else:
            lock.release()
            break
        
        response=download_video(result,choice,episode)
        if not response.ok:
            print(f"{c_red}failed to download episode {episode}{c_reset}")
            print("retrying in 30 seconds................")
            time.sleep(30)
            response=download_video(result,choice,episode)
            if not response.ok:
                print(f"failed to download episode {episode}")
                print("retrying in 30 seconds................")
                time.sleep(30)
                response=download_video(result,choice,episode)
                if not response.ok:
                    print(f"{c_red}Couldn't donwload episode {episode}{c_reset}")
                    failures.append(episode)
                    continue
        with open(f"{output_dir}/{result[choice]}-{episode}.mp4","wb") as ifile:
            for chunk in response.iter_content(chunk_size=1024*1024*10):
                if chunk:
                    ifile.write(chunk)
        print(f"{c_magenta}Donwloaded episode {episode}{c_reset}")
        print(response.status_code,response.headers)


if __name__ == "__main__":
    if not query:
        query=get_search_query()
    result=search_anime(query)
    while(len(result)==0):
        query=get_search_query()
        result=search_anime(query)
    choice=anime_selection(result)
    # print(choice)
    if is_download:
        start,end=episode_selection(result,choice)
        workload=[i for i in range(start,end+1)]
        threads=[]
        for i in range(num_of_connection):
            t=Thread(target=download,args=(result,choice),)
            t.start()
            threads.append(t)
        for i in threads:
            i.join()
            
    else:
        print("only downloading works for now")
    if len(failures)!=0:
        print(f"{c_red}list of the episodes that couldn't be downloaded {failures}{c_reset}")
    
    
    