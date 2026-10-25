"""Common given names: a signal that a capitalized phrase names a person.

Capitalization alone cannot tell "Ayşe Kaya" from "Smart Solutions". A list of repeated phrases
in which many start with a known given name is a list of people. The lexicon is a ranking
signal, never a filter: rare names still pass when their block carries a title or a role.
Keys are folded (see `fold`), so "Şükrü", "Sukru" and "ŞÜKRÜ" are one entry.
"""

import unicodedata


def fold(word):
    word = word.replace("ı", "i").replace("İ", "I")
    word = unicodedata.normalize("NFKD", word.casefold())
    return "".join(c for c in word if c.isalpha() and not unicodedata.combining(c))


def folded(text):
    return {fold(w) for w in text.split() if fold(w)}


TURKISH = folded("""
Abdullah Abdulkadir Abdurrahman Adem Adil Adnan Ahmet Akın Alaattin Alattin Ali Alican Alp Alper
Alparslan Altan Anıl Arda Arif Arman Aslan  Atakan Atalay Atilla Avni Aydın Aydoğan Ayhan Aykut
Aytaç Aziz Bahadır Bahattin Bahaeddin Baran Barış Batuhan Battal Bayram Bekir Berk Berkay Berke
Bilal Bilgehan Bora Bülent Burak Burhan Can Caner Celal Cem Cemal Cemil Cenk Cengiz Cevdet Cihan
Coşkun Cüneyt Çağatay Çağlar Çağrı Çetin Davut Deniz Doğan Doğu Doğukan Doğuş Durmuş Ecevit Efe
Ekrem Emin Emir Emrah Emre Ender Engin Enis Enver Erdal Erdem Erdinç Erdoğan Eren Ergin Ergün Erhan
Erkan Erkay Ersin Ertan Ertuğrul Erol Ersoy Eyüp Fahri Faruk Fatih Ferhat Ferit Fethi Fevzi Fikret
Furkan Gani Gökay Gökhan Göksel Gürkan Güven Hakan Hakkı Halil Halit Haluk Hamdi Hamit Hamza Harun
Hasan Haşim Hayati Haydar Hikmet Hilmi Hulusi Hüseyin Hüsnü İbrahim İhsan İlhan İlker İlkay İlyas
İrfan İsa İshak İsmail İsmet İzzet Kaan Kadir  Kamil Kamer Kaya Kazım Kemal Kenan Kerem
Kerim Koray Korkmaz Kubilay Kudret Kutay   Levent Mahir Mahmut Mehmet Melih Mert Mesut
Metin Mithat Muammer Muhammed Muhammet Muharrem Muhittin Muhsin Murat Musa Mustafa Mutlu Muzaffer
Necati Necdet Necip Nedim Nejat Nevzat Nihat Niyazi Nuh Numan Nuri Nusret Oğuz Oğulcan Oğuzhan Okan
Oktay Onur Orhan Osman Ozan Ömer Önder Özcan Özer Özgür Özkan Polat Rahmi Ramazan Rasim Recep
Reşat Ridvan Rıza Rifat Rüştü Sabri Sadık  Sait Salih Sami Savaş Sedat Selahattin Selçuk
Selim Semih Sencer Serdar Serhat Serkan Sertaç  Sezai Sezgin Sinan Soner Suat Süha Süleyman
Şaban Şahin Şefik Şenol Şerafettin Şeref Şevket Şükrü Tahir Tahsin Talat Taner Tamer Tanju Tarık
Tayfun Taylan Tekin Timur Tolga Tolunay  Tufan Tuğrul Tuncay Tunç Turan Turgay Turgut Uğur
Ulaş Umut Utku Ümit Vahit  Vedat Veli Volkan Yakup Yalçın Yasin Yaşar Yavuz Yener Yiğit
 Yıldırım Yılmaz Yunus Yusuf Yüksel Zafer Zeki Ziya Zübeyir Barbaros Batu Berkan Ceyhun
Abdulkerim Abdülkadir  Bilge Cahit Ercan Erkut Feridun Gürcan Hayri Kâmil Kemalettin Nazım
Orçun Özgen Rauf Sabahattin Sefa Şemsettin Tevfik Uygar Ünal Yekta Zekai
Ayşe Fatma Emine Hatice Zeynep Elif Meryem Şerife Zehra Sultan Hanife Merve Havva Zeliha Esra
Fadime Özlem Hacer Yasemin Hülya Cemile Sevgi Gülsüm Leyla Dilek Büşra Aysel Songül Kübra Hüsniye
Rabia Tuğba Melek Hande Gizem Ebru Derya Ayten Aynur Selin Seda Sibel Esin Ecem Ece Pınar Burcu
Burçin Banu Bahar Başak Belgin Berna Berrin Betül Beyza Canan Ceren Çiğdem Damla Defne Demet Didem
Dilara Duygu Ebru Eda Ekin Elçin Elvan Emel Esma Feride Figen Filiz Funda Füsun Gamze Gaye Gönül
Gözde Gül Gülay Gülşen Gülten Güzin Hale Halime Hilal İclal İlknur İnci İpek İrem Jale Kader Lale
Mehtap Melike Melis Meltem Mine Müge Nalan Nazlı Nermin Nesrin Neslihan Nihal Nilay Nilüfer Nur
Nuray Nurcan Nurhan Oya Öykü Özge Perihan Pelin Rana Reyhan Saadet Sabiha Saliha Sanem Selda Selma
Semra Senem Serap Serpil Sevda Sevim Sevinç Sezen Sinem Suna Şebnem Şeyma Şule Tülay Tülin Türkan
Ülkü Ümran Yağmur Yeliz Yeşim Zerrin Zuhal Aslı Arzu Aylin Aynur Ayça Aysu Azra Begüm Beril Buket
Cansu Ceyda Deniz Dilan Duru Esen Eylül Feyza Gülhan   Irmak Işıl   Meral
 Nevin Nihan Özden Sevil Tuba Yıldız Zişan  Hazal Gülşah Gülnur Aysun Ayşegül Fulya
""")
ENGLISH_EUROPEAN = folded("""
Aaron Adam Adrian Alan Albert Alberto Alec Alex Alexander  Alexandre Alfred Allan Allen
Andrea Andreas Andrew Andy Angelo Anthony Antoine Anton Antonio Arnold Arthur   Austin
Barry Ben  Benjamin Bernard Bert Bill  Blair Bob Boris Brad Bradley Brandon Brendan
Brian Bruce Bruno Bryan Calvin Carl Carlo Carlos Chad Charles Charlie Chris Christian Christoph
Christopher Claude Claudio Clifford Colin Craig  Daniel Daniele Danny Dario David Dean Denis
Dennis Derek Dmitry Dominic Donald Douglas Duncan Dylan Ed Eddie Edgar Edward Edwin Elias Eliot
Emil Emmanuel Enrico Eric Erik Ernest Ethan Eugene Evan Fabio Felix Fernando Filip Florian Francesco
Francis Francisco Frank Franz Fred Frederick Gabriel Gary Gautam  Geoffrey Georg George
Gerald Gerard Gerhard Giovanni Giuseppe Glen Gordon Graham Greg Gregory Guido Gustavo Hans Harold
Harry Hector Heinz Helmut  Henri Henry Herbert Howard Hugo Ian Igor Isaac Ivan Jack Jacob
Jacques Jake James Jan Jason Javier Jean Jeff Jeffrey Jens Jeremy Jerome Jesse Jim Jimmy Joan Joe
Joel Johan Johannes John Jon Jonathan Jordan Jorge Jose José Joseph Josh Joshua Juan Julian Julien
Justin Karl Keith Ken Kenneth Kevin  Klaus Konstantin Kurt Kyle Lars Laurent Lawrence Leo Leon
Leonardo Leslie Lewis Lionel Lorenzo Louis Luca Lucas  Luis Luke Manuel Marc Marcel Marcelo
Marco Marcus Mario Mark Marshall Martin Mathieu Matt Matteo Matthew Matthias Maurice Max Maxim
Michael Michał Michel Miguel Mike Mikhail  Nathan Neil Nicholas Nick Nicola Nicolas Niels
Nigel Noah Norbert Oliver Olivier Oscar Owen Pablo Patrick Paul Paolo Pascal Patrice Pavel Pedro
Peter Phil Philip Philippe Pierre Rafael Ralph Ramon Randall Raphael Raymond Reinhard Rene René
Riccardo Richard Rick Rob Robert Roberto Robin  Roger Roland Roman Romain Ron Ronald Ross Roy
Ruben Russell Ryan Salvatore Sam Samuel Sandro Scott Sean Sebastian Sergey Sergio Seth Simon Stefan
Stefano Stephen Steve Steven Stuart Sven Theodore  Thomas Tim Timothy Tobias Todd Tom Tony
 Travis Trevor Tristan Ulrich Valentin Victor Vincent Vladimir Walter Warren Wayne Werner
William Willem Wolfgang Xavier Yann Yves Zachary Abigail Ada Agnes Alexandra Alice Alicia Alison
Amanda Amy Ana Anastasia Andrea Angela Anna Anne Annie Ashley Audrey Barbara Beatrice Bianca Brenda
Carla Carmen Carol Caroline Carolina Catherine Cecilia Charlotte Chloe Christina Christine Claire
Clara Claudia Cynthia Daniela Deborah Diana Donna Dorothy Elena  Elisa Elizabeth Ella Ellen
Emily Emma Erica Eva Evelyn Faith  Francesca Gabriela Gail Grace Hannah Heather Helen Helena
Ingrid Irene Isabel Isabella Jacqueline Jane Janet Jennifer Jessica Joanna Josephine Julia Juliana
Julie Karen Kate Katherine Kathleen Katrin Kelly Kim Kristin Laura Lauren Lea Lena Linda Lisa Lucia
Lucy Lydia Madeleine Magdalena Margaret Maria Marie Marina Marion Martha Mary Maryam Megan Melanie
Melissa Michelle Monica Nadia Nancy Natalia Natasha Nicole Nina Olga Olivia Pamela Patricia Paula
Rachel Rebecca Renee Renée Rosa  Rose Ruth Sabine Sandra Sara Sarah Sheila Silvia Sofia Sonia
Sophia Sophie Stephanie Susan Suzanne  Teresa Tina Valentina Valerie Vanessa Vera Veronica
Victoria Virginia Wendy Yvonne Zoe
""")
ARABIC_LATIN = folded("""
Abdel Abdelrahman Abdul Abdulaziz Abdulla Abdulrahman Ahmad Ahmed Ali Amin Amir Amr Anas Ashraf Ayman
Bader Bassam Fadi Fahad Faisal Farid Fawaz Hamad Hamid Hani Hassan Hatem Hesham Hisham Hussein
Ibrahim Imad Isam Ismail Jamal Kareem Karim Khaled Khalid Mahmoud Majed Majid Marwan Mazen Mohamed
Mohammad Mohammed Muhammad Mostafa Mustafa Nabil Nader Nasser Omar Osama Rami Riyad Saad Saeed Said
Salah Saleh Salem Sami Samir Sultan Tamer Tarek Tariq Waleed Walid Yasser Youssef Yousef Zaid Ziad
Aisha Amal Amira Asma Dalia Dina Fatima Hala Hanan Hiba Huda Iman Laila Layla Leila Lina Maha
Mariam Mona Nadia Nour Noura Rania Reem Rim Salma Samira Sana Yasmin Zainab Zeinab  
""")
ASIAN_OTHER = folded("""
 Akshay  Amit Anand   Ankit Anupam Arjun Ashish   
 Deepak Gaurav  Hari Harish  Jayant  Karan Karthik Kartik Krishna
 Lakshmi Manish Mohan  Naveen  Nitin Pankaj Prakash  Rahul Rajesh Rakesh
Ramesh Ravi  Rohit Sachin Sanjay Sanjeev Sanjay Santosh  Siddharth  
Sumit Sunil Suresh   Tushar Varun Vijay Vikram Vishal Vivek  Aditi Anjali
Divya Kavya Meera Neha Nisha Pooja Priya Shreya Sneha Sunita Swati Ali Amir Arash Babak Behnam
Farzad Hamed Hossein Mehdi  Mohsen Navid Omid Payam Reza Saeed Shahram Shirin Azadeh Maryam
Farzaneh  Nasrin Parisa Neda Wei Wen Yi Yu Li Jun Jian Hao Hong Xin   Yang Ying
Zhang Chen Feng Jie Lei Ming Qi Qiang Rui Tao Yan Yun Zhen Zhong Hiroshi Kenji Takeshi Yuki Akira
Satoshi Haruki Min Jae Ji Seung Sung Hyun Jin Young Dong Kyung Thanh Minh Duc
""")
GIVEN_NAMES = TURKISH | ENGLISH_EUROPEAN | ARABIC_LATIN | ASIAN_OTHER


def known_given_name(word):
    return fold(word) in GIVEN_NAMES
